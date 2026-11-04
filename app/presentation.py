"""Jinja presentation helpers shared by page and API responses."""
from flask import render_template, url_for


def context(view):
    def filter_url(**changes):
        state = dict(view['state'])
        if not set(changes) <= {'selection_start', 'selection_end', 'selection_detector', 'page', 'mode', 'sort', 'row_page', 'timezone'}:
            state.update(selection_start='', selection_end='', selection_detector='')
        if 'page' not in changes:
            state['page'] = 1
        state.update(changes)
        return url_for('dashboard', **state)

    chips = []
    for key in ['host', 'service', 'severity', 'detector']:
        for value in view['state'][key]:
            label = next(f['label'] for f in view['facets'][key] if f['value'] == value)
            chips.append(dict(label=f'{key.title()}: {label}', url=filter_url(**{key: [v for v in view['state'][key] if v != value]})))
    if view['state']['q']:
        chips.append(dict(label=f"Search: {view['state']['q']}", url=filter_url(q='')))
    return dict(view=view, filter_url=filter_url, chips=chips)


def payload(view):
    return dict(view, html=render_template('partials/workspace.html', **context(view)))
