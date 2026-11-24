"""Security/content/provenance tests for local immutable upload staging."""

import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from werkzeug.datastructures import FileStorage

from app.services.uploads import UploadError, stage_file, load_bundle, local_file, directory


LINE = b'- 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.363779 R02-M1-N0-C:J12-U11 RAS KERNEL INFO example\n'


class UploadStagingTests(unittest.TestCase):
    def setUp(self):
        base = Path('.local/upload-unit-tests')
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base.resolve())
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.mock = patch('app.services.uploads.UPLOAD_ROOT', self.root)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def stage(self, content=LINE, name='bgl.log'):
        return stage_file(FileStorage(stream=io.BytesIO(content), filename=name))

    def expected(self, bundle):
        return dict(bundle['manifest'], manifest_sha256=bundle['manifest_sha256'])

    def assert_rejected(self, content, name='bgl.log', code=None):
        with self.assertRaises(UploadError) as caught:
            self.stage(content, name)
        if code:
            self.assertEqual(caught.exception.code, code)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_txt_log_preserve_exact_original_bytes_and_line_endings(self):
        original = LINE.replace(b'\n', b'\r\n') + LINE.rstrip(b'\n')
        for extension in ('txt', 'LOG'):
            with self.subTest(extension=extension):
                bundle = self.stage(original, 'actual.' + extension)
                manifest, folder = load_bundle(bundle['upload_id'], self.expected(bundle))
                self.assertEqual((folder / manifest['original_key']).read_bytes(), original)
                self.assertEqual(manifest['original_sha256'], hashlib.sha256(original).hexdigest())
                self.assertEqual(manifest['normalized_sha256'], manifest['original_sha256'])
                self.assertEqual(manifest['valid_lines'], 2)
                self.assertEqual(manifest['label_source'], 'uploaded-bgl')
                with ZipFile(folder / 'normalized.zip') as archive:
                    self.assertEqual(archive.namelist(), [manifest['member']])
                    self.assertEqual(archive.read(manifest['member']), original)

    def test_posix_permissions_preserve_the_manifest_hash_contract(self):
        # Exercise macOS/Linux permission handling without changing the host's
        # global os.name or pathlib flavour when this test runs on Windows.
        with patch('app.services.uploads.os', SimpleNamespace(name='posix')):
            bundle = self.stage()
        manifest_path = directory(bundle['upload_id']) / 'manifest.json'
        self.assertEqual(bundle['manifest_sha256'], hashlib.sha256(manifest_path.read_bytes()).hexdigest())
        manifest, _ = load_bundle(bundle['upload_id'], self.expected(bundle))
        self.assertEqual(manifest['valid_lines'], 1)

    def test_private_storage_failure_rejects_before_original_bytes_are_written(self):
        with patch('app.services.uploads.protect_directory', side_effect=UploadError('upload_storage', 'Unavailable', 503)):
            self.assert_rejected(LINE, code='upload_storage')

    def test_windows_acl_uses_sid_and_fails_closed(self):
        from app.services.uploads import protect_directory
        options = SimpleNamespace(name='nt')
        whoami = SimpleNamespace(stdout=b'"host\\operator","S-1-5-21-1000"\r\n')
        # Keep pathlib and the platform untouched; only this module's OS branch
        # and process boundary are simulated on a non-Windows test host.
        with patch('app.services.uploads.os', options), patch('app.services.uploads.subprocess.run', side_effect=[whoami, SimpleNamespace(returncode=0)]) as run:
            with patch.object(subprocess, 'CREATE_NO_WINDOW', 0x08000000, create=True):
                protect_directory(self.root)
            args = run.call_args_list[1].args[0]
            self.assertIn('*S-1-5-21-1000:(OI)(CI)F', args)
            self.assertIn('/inheritance:r', args)
            self.assertTrue(run.call_args.kwargs['check'])
        with patch('app.services.uploads.os', options), patch('app.services.uploads.subprocess.run', side_effect=OSError('denied')):
            with patch.object(subprocess, 'CREATE_NO_WINDOW', 0x08000000, create=True):
                with self.assertRaises(UploadError) as caught:
                    protect_directory(self.root)
            self.assertEqual(caught.exception.status, 503)

    def test_csv_original_and_explicit_physical_row_mapping_are_distinct(self):
        buffer = io.StringIO(newline='')
        writer = csv.writer(buffer)
        writer.writerow(['raw_line'])
        writer.writerow([LINE.decode().replace('\n', '\r\n')])
        writer.writerow([LINE.decode().rstrip('\n')])
        original = b'\xef\xbb\xbf' + buffer.getvalue().encode()
        bundle = self.stage(original, 'source.csv')
        manifest, folder = load_bundle(bundle['upload_id'], self.expected(bundle))
        self.assertEqual((folder / 'original.csv').read_bytes(), original)
        self.assertNotEqual(manifest['normalized_sha256'], manifest['original_sha256'])
        mapping = [json.loads(row) for row in (folder / 'mapping.jsonl').read_text().splitlines()]
        self.assertEqual([row['csv_row'] for row in mapping], [2, 3])
        self.assertEqual(mapping[0]['csv_physical_line_start'], 2)
        self.assertGreater(mapping[0]['csv_physical_line_end'], mapping[0]['csv_physical_line_start'])
        self.assertNotIn('original_byte_offset', mapping[0])
        self.assertEqual(mapping[1]['bgl_byte_offset'], len(LINE))
        with ZipFile(folder / 'normalized.zip') as archive:
            self.assertEqual(archive.read(manifest['member']), LINE + LINE)

    def test_mixed_malformed_rows_are_preserved_and_counted(self):
        data = LINE + b'malformed text without BGL fields\n'
        bundle = self.stage(data)
        manifest, folder = load_bundle(bundle['upload_id'], self.expected(bundle))
        self.assertEqual((manifest['valid_lines'], manifest['malformed_rows'], manifest['total_lines']), (1, 1, 2))
        with ZipFile(folder / 'normalized.zip') as archive:
            self.assertEqual(archive.read(manifest['member']), data)

    def test_filename_traversal_and_unsupported_extensions_are_rejected(self):
        for name in ('../file.log', 'sub/file.log', 'sub\\file.log', 'C:\\file.log', '.env.log', 'name\x00.log', 'line\n.log', 'x.exe', 'source.zip'):
            with self.subTest(name=name):
                self.assert_rejected(LINE, name)

    def test_binary_encoding_bom_empty_and_non_bgl_are_rejected(self):
        for content in (b'', b'\x00\x01' + LINE, b'\xff' + LINE, b'\xef\xbb\xbf' + LINE,
                        b'<script>alert(1)</script>\n', b'print("hello")\n'):
            with self.subTest(content=content[:20]):
                self.assert_rejected(content)

    def test_carriage_return_only_files_are_rejected_precisely(self):
        # Classic Mac line endings: three rows used to collapse into one "valid" event.
        self.assert_rejected(LINE.replace(b'\n', b'\r') * 3, code='invalid_line_break')
        # Over the per-line limit the error must still name the line endings, not the size.
        self.assert_rejected(LINE.replace(b'\n', b'\r') * 3000, code='invalid_line_break')
        bundle = self.stage(LINE.replace(b'\n', b'\r\n') * 2)
        self.assertEqual(bundle['manifest']['valid_lines'], 2)

    def test_csv_schema_columns_and_embedded_line_break_are_rejected(self):
        for content in (b'timestamp,message\n1,hello\n', b'raw_line,raw_line\nx,y\n',
                        b'raw_line\nx,y\n', b'raw_line\n"abc\nnot one line"\n'):
            with self.subTest(content=content):
                self.assert_rejected(content, 'data.csv')

    def test_file_and_row_caps_remove_only_unaccepted_staging(self):
        with patch('app.services.uploads.MAX_FILE_BYTES', 32):
            self.assert_rejected(LINE, code='file_too_large')
        with patch('app.services.uploads.MAX_ROWS', 1):
            self.assert_rejected(LINE + LINE, code='upload_limit')
        with patch('app.services.uploads.MAX_LINE_BYTES', 32):
            self.assert_rejected(LINE, code='upload_limit')

    def test_worker_validation_detects_original_zip_mapping_and_manifest_mutation(self):
        for name in ('original.log', 'normalized.zip', 'mapping.jsonl', 'manifest.json'):
            with self.subTest(name=name):
                bundle = self.stage()
                expected = self.expected(bundle)
                folder = directory(bundle['upload_id'])
                with (folder / name).open('ab') as output:
                    output.write(b'changed')
                with self.assertRaisesRegex(UploadError, 'checksum'):
                    load_bundle(bundle['upload_id'], expected)

    def test_invalid_opaque_ids_and_symlink_candidates_fail_closed(self):
        for upload_id in ('../escape', 'f' * 31, 'G' * 32, 'f' * 33):
            with self.subTest(upload_id=upload_id), self.assertRaises(Exception):
                directory(upload_id)
        with patch.object(Path, 'is_symlink', return_value=True):
            with self.assertRaises(UploadError):
                local_file(self.root, 'original.log')

    def test_html_like_message_is_kept_as_data_without_execution(self):
        raw = LINE.replace(b'example', b'<script>window.bad=true</script>')
        bundle = self.stage(raw)
        manifest, folder = load_bundle(bundle['upload_id'], self.expected(bundle))
        self.assertEqual(manifest['valid_lines'], 1)
        self.assertEqual((folder / 'original.log').read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
