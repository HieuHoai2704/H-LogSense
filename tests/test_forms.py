"""Real Flask-WTF validation and default per-form CSRF, without a database."""

import io
import os
import unittest
from unittest.mock import patch

from flask import Flask, jsonify
from flask_wtf.csrf import generate_csrf
from werkzeug.datastructures import MultiDict

from app.forms import DatasetCreateForm, DatasetDeleteForm, DatasetRenameForm, UploadForm


class WorkspaceFormsTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='synthetic-test-form-signing-secret')
        classes = {'create': DatasetCreateForm, 'rename': DatasetRenameForm,
                   'delete': DatasetDeleteForm, 'upload': UploadForm}

        @self.app.get('/token')
        def token():
            return jsonify(csrf_token=generate_csrf())

        @self.app.post('/probe/<kind>')
        def probe(kind):
            form = classes[kind]()
            valid = form.validate_on_submit()
            return jsonify(valid=valid, errors=form.errors), 200 if valid else 400

        self.client = self.app.test_client()

    def token(self, client=None):
        return (client or self.client).get('/token').json['csrf_token']

    def create(self, **changes):
        values = {'name': 'BGL study', 'dataset_key': 'bgl-study', 'data_mode': 'unverified',
                  'csrf_token': self.token()}
        values.update(changes)
        return self.client.post('/probe/create', data=values)

    def test_default_csrf_is_enabled_even_in_testing(self):
        self.assertTrue(self.app.config.get('WTF_CSRF_ENABLED', True))
        self.assertEqual(self.create().status_code, 200)
        response = self.client.post('/probe/create', data={
            'name': 'Study', 'dataset_key': 'study', 'data_mode': 'unverified'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('csrf_token', response.json['errors'])

    def test_private_form_route_error_responses_are_not_cached(self):
        from app import create_app
        with patch.dict(os.environ, {}, clear=True):
            app = create_app({'TESTING': True})
            response = app.test_client().post('/forms/datasets', data={})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_invalid_signed_csrf_rejected(self):
        response = self.create(csrf_token='forged-token')
        self.assertEqual(response.status_code, 400)
        self.assertIn('csrf_token', response.json['errors'])

    def test_token_from_another_session_rejected(self):
        token = self.token()
        other = self.app.test_client()
        self.token(other)
        response = other.post('/probe/rename', data={'name': 'Other', 'csrf_token': token})
        self.assertEqual(response.status_code, 400)
        self.assertIn('csrf_token', response.json['errors'])

    def test_expired_token_rejected_without_disabling_protection(self):
        token = self.token()
        self.app.config['WTF_CSRF_TIME_LIMIT'] = -1
        response = self.client.post('/probe/rename', data={'name': 'Later', 'csrf_token': token})
        self.assertEqual(response.status_code, 400)
        self.assertIn('expired', response.json['errors']['csrf_token'][0].lower())

    def test_name_bounds_whitespace_and_controls(self):
        for value in ('', '   ', 'x' * 201, 'new\x00name', 'name\nline'):
            with self.subTest(value=repr(value)):
                response = self.create(name=value)
                self.assertEqual(response.status_code, 400)
                self.assertIn('name', response.json['errors'])
        self.assertEqual(self.create(name='<img src=x> literal text').status_code, 200)

    def test_invalid_unicode_label_has_field_error(self):
        with self.app.test_request_context('/probe/create', method='POST'):
            token = generate_csrf()
            form = DatasetCreateForm(formdata=MultiDict({
                'name': '\ud800', 'dataset_key': 'valid-key', 'data_mode': 'real', 'csrf_token': token}))
            self.assertFalse(form.validate_on_submit())
            self.assertIn('name', form.errors)

    def test_key_and_mode_are_validated(self):
        for value in ('../escape', 'a b', '-starts', 'x' * 101, 'khóa'):
            with self.subTest(key=value):
                response = self.create(dataset_key=value)
                self.assertEqual(response.status_code, 400)
                self.assertIn('dataset_key', response.json['errors'])
        self.assertEqual(self.create(data_mode='invented').status_code, 400)

    def test_optional_source_and_numeric_bounds(self):
        self.assertEqual(self.create(source_id='').status_code, 200)
        self.assertEqual(self.create(source_id='12').status_code, 200)
        for value in ('0', '-1', str(2**63), '1.2', 'NaN'):
            with self.subTest(source=value):
                response = self.create(source_id=value)
                self.assertEqual(response.status_code, 400)
                self.assertIn('source_id', response.json['errors'])

    def test_rename_is_a_used_signed_form(self):
        response = self.client.post('/probe/rename', data={'name': 'Renamed', 'csrf_token': self.token()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post('/probe/rename', data={'name': 'Renamed'}).status_code, 400)

    def test_delete_requires_confirmation_and_signed_token(self):
        token = self.token()
        for value in ('', 'false', '0'):
            response = self.client.post('/probe/delete', data={'confirmation': value, 'csrf_token': token})
            self.assertEqual(response.status_code, 400)
            self.assertIn('confirmation', response.json['errors'])
        self.assertEqual(self.client.post('/probe/delete', data={'confirmation': 'y', 'csrf_token': token}).status_code, 200)
        self.assertEqual(self.client.post('/probe/delete', data={'confirmation': 'y'}).status_code, 400)

    def upload(self, filename='source.log', **changes):
        values = {'dataset_id': '1', 'idempotency_key': 'upload-001', 'csrf_token': self.token(),
                  'file': (io.BytesIO(b'- 1117838570 example\n'), filename)}
        values.update(changes)
        return self.client.post('/probe/upload', data=values, content_type='multipart/form-data')

    def test_upload_file_presence_extension_and_signed_token(self):
        for filename in ('source.log', 'source.TXT', 'source.csv'):
            self.assertEqual(self.upload(filename).status_code, 200)
        self.assertEqual(self.upload('script.exe').status_code, 400)
        response = self.client.post('/probe/upload', data={
            'dataset_id': '1', 'idempotency_key': 'missing-file', 'csrf_token': self.token()})
        self.assertEqual(response.status_code, 400)
        self.assertIn('file', response.json['errors'])
        response = self.upload(csrf_token='bad')
        self.assertEqual(response.status_code, 400)
        self.assertIn('csrf_token', response.json['errors'])

    def test_upload_dataset_and_reference_validation(self):
        for value in ('0', '-2', str(2**63), 'not-id'):
            response = self.upload(dataset_id=value)
            self.assertEqual(response.status_code, 400)
            self.assertIn('dataset_id', response.json['errors'])
        self.assertEqual(self.upload(idempotency_key=' ').status_code, 400)
        self.assertEqual(self.upload(idempotency_key='x' * 101).status_code, 400)
