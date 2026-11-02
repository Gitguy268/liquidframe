"""Companion access, source serving and catalog-copy privacy boundaries."""
import json
import pytest
from fastapi.testclient import TestClient
from openphoto import catalog, store, workspaces
from openphoto.api import app
from openphoto import photobook


def test_companion_routes_and_policy(tmp_path, monkeypatch):
    out = tmp_path / 'photobook'
    out.mkdir()
    (out / 'index.html').write_text('<h1>Local photobook</h1>')
    (out / 'csp.json').write_text(json.dumps(['example-hash']))
    (out / 'source.zip').write_bytes(b'PK-source')
    (out / 'engine.wasm').write_bytes(b'\0asm')
    monkeypatch.setattr(photobook, 'output_root', lambda: out)
    with TestClient(app) as client:
        assert client.post('/api/v1/photobook/selection', json={'selection': {'ids': []}}, headers={'X-Openphoto': '1'}).status_code == 401
        page = client.get('/photobook')
        assert page.status_code == 200 and 'Local photobook' in page.text
        policy = page.headers['content-security-policy']
        assert "'sha256-example-hash'" in policy and "'wasm-unsafe-eval'" in policy
        assert 'https:' not in policy and "script-src 'self' 'unsafe-inline'" not in policy
        assert client.get('/photobook/source.zip').content == b'PK-source'
        assert 'attachment' in client.get('/photobook/source.zip').headers['content-disposition']
        assert client.get('/photobook/engine.wasm').headers['content-type'] == 'application/wasm'
        assert client.get('/photobook/missing.js').status_code == 404
        # The main app keeps its original strict policy.
        assert "'wasm-unsafe-eval'" not in client.get('/').headers['content-security-policy']
        assert client.post('/api/v1/photobook/selection', json={'selection': {'ids': []}}).status_code == 403


def test_missing_companion_reports_build_instructions(tmp_path, monkeypatch):
    monkeypatch.setattr(photobook, 'output_root', lambda: tmp_path / 'not-built')
    with TestClient(app) as client:
        page = client.get('/photobook/')
        assert page.status_code == 503 and 'build-photobook.mjs' in page.text


def test_selection_and_edited_png_do_not_modify_source(asset):
    original = store.asset_path(asset).read_bytes()
    result = photobook.selection(photobook.ImportRequest(selection={'ids': [asset['id'], asset['id']]}))
    assert len(result['photos']) == 1
    assert result['photos'][0]['name'] == 'summer.png'
    first = photobook.photo(asset['id'])
    assert first.media_type == 'image/png' and first.body.startswith(b'\x89PNG')
    store.save_recipe(asset['id'], {'adjustments': {'exposure': 1}}, 0)
    edited = photobook.photo(asset['id'])
    assert edited.body != first.body
    assert store.asset_path(asset).read_bytes() == original
    snapshot = catalog.snapshot({})
    with pytest.raises(ValueError, match='between 1 and 100'):
        photobook.selection(photobook.ImportRequest(selection={**snapshot, 'exclude_ids': [asset['id']]}))


def test_private_trash_and_video_never_enter_browser_books(asset):
    workspaces.setup_passcode('photobook-test')
    catalog.patch_assets([asset['id']], {'hidden': 1})
    with pytest.raises(PermissionError):
        photobook.photo(asset['id'])
    # Even an active private lease must not allow persistent copies into books.
    with workspaces.using(workspaces.resolve(), True):
        for request in (lambda: photobook.photo(asset['id']), lambda: photobook.selection(photobook.ImportRequest(selection={'ids': [asset['id']]}))):
            with pytest.raises(PermissionError): request()
        catalog.patch_assets([asset['id']], {'hidden': 0})
        catalog.remove([asset['id']])
        with pytest.raises(PermissionError): photobook.photo(asset['id'])
        catalog.patch_assets([asset['id']], {'deleted_at': None, 'purged': 0})
    store.execute("UPDATE assets SET media_kind='video' WHERE id=?", (asset['id'],))
    with pytest.raises(ValueError, match='Videos'):
        photobook.photo(asset['id'])


def test_handoff_limits_and_library_isolation(asset, tmp_path):
    with pytest.raises(ValueError):
        photobook.ImportRequest(selection={'ids': ['x'] * 101})
    with workspaces.using(workspaces.LibraryContext('other', tmp_path / 'other', 'Other')):
        store.init()
        with pytest.raises((ValueError, FileNotFoundError)):
            photobook.photo(asset['id'])
