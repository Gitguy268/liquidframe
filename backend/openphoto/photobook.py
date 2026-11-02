"""HTTP adapter for the separately licensed, static Ente Photobook companion."""
from pathlib import Path
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from . import store, catalog, imaging

router = APIRouter()

class PhotoSelection(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=100)
    selection_id: str | None = Field(default=None, max_length=100)
    exclude_ids: list[str] = Field(default_factory=list, max_length=100000)

class ImportRequest(BaseModel):
    selection: PhotoSelection

def output_root():
    return store.PROJECT / 'companions' / 'photobook' / 'out'

def policy():
    manifest = output_root() / 'csp.json'
    hashes = json.loads(manifest.read_text()) if manifest.is_file() else []
    scripts = " ".join("'sha256-" + value + "'" for value in hashes)
    return ("default-src 'self'; script-src 'self' 'wasm-unsafe-eval' " + scripts +
            "; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; "
            "connect-src 'self' blob:; font-src 'self'; worker-src 'self' blob:; "
            "media-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")

def importable(asset_id):
    asset = store.get_asset(asset_id)
    # Browser books outlive private-view leases: never persist protected media here.
    if asset.get('hidden') or asset.get('deleted_at'):
        raise PermissionError('Private items cannot be copied into browser photobooks.')
    if asset.get('media_kind') == 'video':
        raise ValueError('Select photos only. Videos cannot be added to a photobook.')
    return asset

@router.post('/api/v1/photobook/selection')
def selection(body: ImportRequest):
    ids = list(dict.fromkeys(catalog.ids(body.selection.model_dump())))
    if not ids or len(ids) > 100:
        raise ValueError('Select between 1 and 100 photos for a photobook.')
    photos = []
    for asset_id in ids:
        asset = importable(asset_id)
        photos.append({'id': asset_id, 'name': Path(asset['name']).stem + '.png', 'captured': asset.get('captured', '')})
    return {'photos': photos}

@router.get('/api/v1/photobook/photos/{asset_id}')
def photo(asset_id: str):
    asset = importable(asset_id)
    recipe = store.get_recipe(asset_id)['recipe']
    store.validate_operations(asset_id, recipe)
    rgb, alpha, _ = imaging.render(store.asset_path(asset), recipe, preview=6000)
    pixels = imaging.display(rgb, alpha)
    return Response(pixels.write_to_buffer('.png'), media_type='image/png', headers={'Cache-Control': 'no-store'})

@router.get('/photobook', include_in_schema=False)
def redirect():
    return RedirectResponse('/photobook/')

@router.get('/photobook/{path:path}', include_in_schema=False)
def companion(path: str):
    root = output_root()
    if not (root / 'index.html').is_file():
        return HTMLResponse('<h1>Photobook is not built yet</h1><p>Run node scripts/build-photobook.mjs from the LiquidFrame folder, then reload.</p><a href="/">Return to LiquidFrame</a>', status_code=503)
    file = store.confined(root, path or 'index.html', must_exist=False)
    if not file.is_file():
        raise HTTPException(404, 'Photobook file not found.')
    return FileResponse(file, filename='ente-photobook-source.zip' if path == 'source.zip' else None)
