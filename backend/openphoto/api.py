from __future__ import annotations
import asyncio, datetime, json, os, re, secrets
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from . import store, jobs, imaging, library, models, exports, catalog, workspaces, media

SESSION=secrets.token_urlsafe(32)

from .schemas import *

@asynccontextmanager
async def lifespan(app):
    for entry in workspaces.registry():
        with workspaces.using(workspaces.resolve(entry['id'])):
            store.init();catalog.expire();jobs.resume()
    library.start_watch()
    yield
    library.stop_watch()
    jobs.stop()

app=FastAPI(title='LiquidFrame',version='0.2.0',lifespan=lifespan,docs_url=None,redoc_url=None)

def session_cookie(request:Request):return f'openphoto_session_{request.url.port or 80}'

@app.middleware('http')
async def local_only(request:Request,call_next):
    host=request.url.hostname
    if host not in ['127.0.0.1','localhost','::1','testserver']:return JSONResponse({'detail':'LiquidFrame is local-only.'},403)
    origin=request.headers.get('origin')
    allowed={f'http://{request.headers.get("host")}',f'https://{request.headers.get("host")}'}
    if origin and origin not in allowed:return JSONResponse({'detail':'Cross-origin requests are blocked.'},403)
    if request.url.path.startswith('/api/'):
        if not secrets.compare_digest(request.cookies.get(session_cookie(request),''),SESSION):return JSONResponse({'detail':'Open the app homepage to begin a local session.'},401)
        if request.method not in ['GET','HEAD'] and request.headers.get('x-openphoto')!='1':return JSONResponse({'detail':'Local session header is required.'},403)
    library_id=request.headers.get('x-library-id') or request.query_params.get('library') or 'default'
    try:context=workspaces.resolve(library_id)
    except ValueError:return JSONResponse({'detail':'Library not found.'},404)
    private_token=request.cookies.get('liquidframe_private_'+str(request.url.port or 80))
    with workspaces.using(context,workspaces.private_unlocked(private_token,library_id)):
        lease=workspaces.LEASE.set((private_token,library_id))
        try:response=await call_next(request)
        finally:workspaces.LEASE.reset(lease)
    if request.url.path.startswith('/api/'):response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'; font-src 'self'; worker-src 'self' blob:; media-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
    if request.url.path.startswith('/photobook/'):
        response.headers['Content-Security-Policy']=photobook.policy()
        if request.url.path=='/photobook/':
            response.set_cookie(session_cookie(request),SESSION,httponly=True,samesite='strict',max_age=86400)
    return response

@app.exception_handler(imaging.pyvips.Error)
async def image_error(request,e):return JSONResponse({'detail':'Cannot process this photo: '+str(e)},422)

@app.exception_handler(ValueError)
async def value_error(request,e):return JSONResponse({'detail':str(e)},409)
@app.exception_handler(FileNotFoundError)
async def missing_file(request,e):return JSONResponse({'detail':'The file or folder is unavailable. Reconnect the drive or select another folder.'},404)
@app.exception_handler(PermissionError)
async def permission(request,e):
    message=str(e)
    if not message.startswith(('Unlock private views','Incorrect passcode')):message='Permission denied. Select a folder your account can access.'
    return JSONResponse({'detail':message},403)

@app.get('/api/v1/status')
def status():
    stats=store.one("SELECT COUNT(*) total,COALESCE(SUM(favorite),0) favorites,COALESCE(SUM(size),0) bytes,COALESCE(SUM(status='missing'),0) missing FROM assets WHERE "+catalog.visibility())
    stats['indexed']=store.one('SELECT COUNT(*) n FROM embeddings e JOIN assets a ON a.id=e.asset_id WHERE '+catalog.visibility(alias='a'))['n']
    return {'stats':stats,'roots':store.rows('SELECT * FROM roots ORDER BY created'),'albums':store.rows('SELECT a.*,COUNT(v.id) count FROM albums a LEFT JOIN album_assets x ON x.album_id=a.id LEFT JOIN assets v ON v.id=x.asset_id AND '+catalog.visibility(alias='v')+' GROUP BY a.id ORDER BY a.position,a.name'),'models':models.status(),'settings':{k:store.setting(k,v) for k,v in [('theme','system'),('glass',True),('cache_gb',10),('acceleration','cpu')]},'jobs':jobs.snapshot()}

@app.get('/api/v1/capabilities')
def capabilities():return {'formats':imaging.formats(),'imagemagick':bool(imaging.MAGICK),'pipeline':'float linear-light; 16-bit PNG/TIFF export','raw':True,'version':'0.2.0'}

@app.get('/api/v1/folders')
def folders(path:str|None=None):
    p=Path(path).expanduser().resolve(strict=True) if path else Path.home()
    if not p.is_dir():raise ValueError('Select a folder.')
    entries=[]
    for e in p.iterdir():
        try:
            if e.is_dir() and not e.is_symlink() and not e.name.startswith('.'):entries.append({'name':e.name,'path':str(e)})
        except OSError:continue
    drives=[]
    if os.name=='nt':drives=[f'{chr(i)}:\\' for i in range(65,91) if Path(f'{chr(i)}:\\').exists()]
    elif Path('/Volumes').exists():drives=['/Volumes']
    else:drives=['/media','/mnt']
    return {'path':str(p),'parent':str(p.parent),'home':str(Path.home()),'folders':sorted(entries,key=lambda e:e['name'].lower()),'drives':drives}

@app.post('/api/v1/roots')
def add_root(body:Folder):
    r=library.add_root(body.path,body.kind);job=None
    if body.kind=='library':job=jobs.create('scan',{'root_id':r['id']});library.refresh_watch()
    return {'root':r,'job_id':job}
@app.post('/api/v1/roots/{root_id}/scan')
def rescan(root_id:str):store.root_path(root_id);return {'job_id':jobs.create('scan',{'root_id':root_id})}
@app.delete('/api/v1/roots/{root_id}')
def detach(root_id:str):
    # Removing a library connection never removes files or orphan a recovery record.
    if store.one('SELECT b.id FROM backups b JOIN assets a ON a.id=b.asset_id WHERE a.root_id=?',(root_id,)):raise ValueError('This folder has protected backups. Keep it connected for in-app restoration.')
    if store.one("SELECT id FROM jobs WHERE state IN ('queued','running') AND payload LIKE ?",('%'+root_id+'%',)):raise ValueError('Wait for this folder’s active tasks before disconnecting it.')
    catalog.detach_root(root_id)
    library.refresh_watch();return {'ok':True}

@app.get('/api/v1/assets')
def assets(offset:int=0,limit:int=120,q:str='',root_id:str|None=None,album_id:str|None=None,person_id:str|None=None,favorite:bool=False,date_from:str='',date_to:str='',format:str='',sort:Literal['newest','oldest','name']='newest',semantic:bool=False):
    return catalog.query(dict(q=q,root_id=root_id,album_id=album_id,person_id=person_id,favorite=favorite,date_from=date_from,date_to=date_to,format=format,sort=sort,semantic=semantic),offset,limit)
@app.get('/api/v1/assets/{asset_id}')
def asset(asset_id:str):return {'asset':store.get_asset(asset_id),**store.get_recipe(asset_id)}
@app.patch('/api/v1/assets/{asset_id}/favorite')
def favorite(asset_id:str,body:Favorite):return catalog.patch_assets([asset_id],{'favorite':int(body.favorite)},'Change favorite')
@app.get('/api/v1/assets/{asset_id}/original')
def original(asset_id:str,size:int=1024,frame:int=0):
    if frame<0 or frame>10000:raise ValueError('Invalid frame.')
    return FileResponse(imaging.preview(asset_id,min(2048,max(64,size)),{'frame':frame}),media_type='image/webp')
@app.get('/api/v1/assets/{asset_id}/history')
def recipe_history(asset_id:str):
    store.get_asset(asset_id)
    values=store.rows('SELECT id,recipe,created FROM recipe_history WHERE asset_id=? ORDER BY created DESC LIMIT 60',(asset_id,))
    for r in values:r['recipe']=json.loads(r['recipe'])
    return list(reversed(values))

@app.get('/api/v1/assets/{asset_id}/thumbnail')
def thumb(asset_id:str,size:int=256):return FileResponse(imaging.preview(asset_id,min(1024,max(64,size))),media_type='image/webp')
@app.post('/api/v1/assets/{asset_id}/preview')
def preview(asset_id:str,body:Preview):
    store.validate_operations(asset_id,body.recipe.model_dump(exclude_none=True))
    store.asset_path(store.get_asset(asset_id),body.revision)
    return FileResponse(imaging.preview(asset_id,body.size,body.recipe.model_dump(exclude_none=True)),media_type='image/webp')
@app.post('/api/v1/assets/{asset_id}/histogram')
def histogram(asset_id:str,body:Preview):
    store.validate_operations(asset_id,body.recipe.model_dump(exclude_none=True))
    a=store.get_asset(asset_id);path=store.asset_path(a,body.revision)
    rgb,_,_=imaging.render(path,body.recipe.model_dump(exclude_none=True),preview=512);pixels=imaging.array(rgb)
    import numpy as np
    return {'channels':[np.histogram(pixels[:,:,i],bins=64,range=(0,256))[0].tolist() for i in range(3)]}
@app.put('/api/v1/assets/{asset_id}/recipe')
def recipe(asset_id:str,body:SaveRecipe):
    store.asset_path(store.get_asset(asset_id),body.revision)
    return store.save_recipe(asset_id,body.recipe.model_dump(exclude_none=True),body.version)
@app.post('/api/v1/assets/{asset_id}/ai')
def ai(asset_id:str,body:AI):
    store.validate_operations(asset_id,body.recipe.model_dump(exclude_none=True))
    store.asset_path(store.get_asset(asset_id),body.revision)
    return {'job_id':jobs.create('ai',{'asset_id':asset_id,**body.model_dump(exclude_none=True)})}
@app.post('/api/v1/assets/{asset_id}/auto')
def auto(asset_id:str,body:Preview):
    import numpy as np
    a=store.get_asset(asset_id);rgb,_,_=imaging.render(store.asset_path(a,body.revision),body.recipe.model_dump(exclude_none=True),preview=256)
    pix=imaging.array(rgb)/255;lum=np.maximum(pix@np.array([.2126,.7152,.0722]),.001)
    exposure=float(np.clip(np.log2(.45/max(float(np.median(lum)),.05)),-1.5,1.5))
    return {'exposure':exposure,'contrast':8,'vibrance':12,'highlights':-10,'shadows':10}

@app.post('/api/v1/albums')
def album(body:Name):
    return catalog.create_album({'name':body.name})
@app.patch('/api/v1/albums/{album_id}')
def rename_album(album_id:str,body:Name):return catalog.album_mutation(album_id,{'name':body.name})
@app.delete('/api/v1/albums/{album_id}')
def delete_album(album_id:str):return catalog.album_mutation(album_id,delete=True)
@app.post('/api/v1/albums/{album_id}/assets')
def album_add(album_id:str,body:AssetIds):
    if not store.one('SELECT id FROM albums WHERE id=?',(album_id,)):raise ValueError('Album not found.')
    with store.db() as c:
        c.executemany('INSERT OR IGNORE INTO album_assets(album_id,asset_id) VALUES(?,?)',[(album_id,a) for a in body.assets])
    return {'ok':True}
@app.delete('/api/v1/albums/{album_id}/assets/{asset_id}')
def album_remove(album_id:str,asset_id:str):store.execute('DELETE FROM album_assets WHERE album_id=? AND asset_id=?',(album_id,asset_id));return {'ok':True}

@app.get('/api/v1/presets')
def presets():
    values=store.rows('SELECT * FROM presets')
    for p in values:p['recipe']=json.loads(p['recipe'])
    return values
@app.post('/api/v1/presets')
def preset(body:Preset):
    # Presets never point at an AI derivative from a different source image.
    p=body.recipe.model_dump(exclude_none=True);p['operations']=[]
    i=store.uid();store.execute('INSERT INTO presets VALUES(?,?,?)',(i,body.name,json.dumps(p)));return {'id':i}
@app.get('/api/v1/people')
def people():return catalog.people()
@app.patch('/api/v1/people/{person_id}')
def person_name(person_id:str,body:Name):
    catalog.authorize_person(person_id)
    store.execute('UPDATE people SET name=? WHERE id=?',(body.name,person_id));return {'ok':True}
@app.post('/api/v1/people/{person_id}/merge')
def merge_people(person_id:str,body:Assign):
    catalog.authorize_person(person_id)
    if body.person_id:catalog.authorize_person(body.person_id)
    if not body.person_id or not store.one('SELECT id FROM people WHERE id=?',(body.person_id,)):raise ValueError('Select a target person.')
    store.execute('UPDATE observations SET person_id=? WHERE person_id=?',(body.person_id,person_id));store.execute('UPDATE faces SET person_id=? WHERE person_id=?',(body.person_id,person_id));store.execute('DELETE FROM people WHERE id=?',(person_id,));return {'ok':True}
@app.get('/api/v1/assets/{asset_id}/faces')
def asset_faces(asset_id:str):
    store.get_asset(asset_id)
    values=store.rows('SELECT id,person_id,box FROM faces WHERE asset_id=?',(asset_id,))
    for x in values:x['box']=json.loads(x['box'])
    return values
@app.patch('/api/v1/faces/{face_id}')
def assign_face(face_id:str,body:Assign):
    f=store.one('SELECT asset_id FROM faces WHERE id=?',(face_id,))
    if not f:raise ValueError('Face not found.')
    store.get_asset(f['asset_id'])
    i=body.person_id
    if i:catalog.authorize_person(i)
    if i is None:i=store.uid();store.execute('INSERT INTO people(id,name,created) VALUES(?,?,?)',(i,'Unnamed person',store.now()))
    store.execute('UPDATE faces SET person_id=? WHERE id=?',(i,face_id));return {'person_id':i}
@app.get('/api/v1/duplicates')
def duplicates():return library.duplicates()
@app.post('/api/v1/analysis')
def analysis(body:Analysis):return {'job_id':jobs.create('analysis',body.model_dump(exclude_none=True))}
@app.post('/api/v1/models/download')
def download(body:Downloads):return {'job_id':jobs.create('model',body.model_dump())}
@app.get('/api/v1/jobs')
def list_jobs():return jobs.snapshot()
@app.post('/api/v1/jobs/{job_id}/cancel')
def cancel(job_id:str):
    job=store.one('SELECT * FROM jobs WHERE id=?',(job_id,))
    if not job:raise ValueError('Task not found.')
    jobs.authorize(job)
    store.execute("UPDATE jobs SET state='cancelled',message='Cancelled' WHERE id=? AND state IN ('queued','running')",(job_id,));return {'ok':True}
@app.post('/api/v1/jobs/{job_id}/retry')
def retry(job_id:str):
    j=store.one('SELECT * FROM jobs WHERE id=?',(job_id,))
    if j:jobs.authorize(j)
    if not j or j['state'] not in ['failed','cancelled']:raise ValueError('Only failed or cancelled jobs can be retried.')
    store.execute("UPDATE jobs SET state='queued',error=NULL WHERE id=?",(job_id,));jobs.submit(job_id);return {'job_id':job_id}
@app.get('/api/v1/events')
async def events(request:Request):
    async def stream():
        last=None
        while not await request.is_disconnected():
            snapshot=json.dumps(jobs.snapshot())
            if snapshot!=last:yield 'data: '+snapshot+'\n\n';last=snapshot
            else:yield ': heartbeat\n\n'
            await asyncio.sleep(1)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache'})
@app.post('/api/v1/exports')
def export(body:Export):
    if not body.replace and not body.output_root:raise ValueError('Choose an output folder.')
    if body.options.bits==16 and body.options.format not in ['png','tif','tiff']:raise ValueError('16-bit output requires PNG or TIFF. Choose 8-bit for this format.')
    p=body.model_dump(exclude_none=True)
    for x in p['assets']:
        if x.get('recipe') is None:x.pop('recipe',None)
        else:store.validate_operations(x['id'],x['recipe'])
        store.asset_path(store.get_asset(x['id']),x['revision'])
    return {'job_id':jobs.create('export',p)}
@app.get('/api/v1/backups')
def backups():return store.rows('SELECT b.id,b.asset_id,b.created,b.restored,a.name FROM backups b JOIN assets a ON a.id=b.asset_id WHERE '+('a.purged=0' if workspaces.PRIVATE.get() else catalog.visibility(alias='a'))+' ORDER BY b.created DESC')
@app.post('/api/v1/backups/restore')
def restore(body:Restore):
    b=store.one('SELECT asset_id FROM backups WHERE id=?',(body.backup_id,))
    if not b:raise ValueError('Backup not found.')
    store.get_asset(b['asset_id']);return {'job_id':jobs.create('restore',body.model_dump())}
@app.put('/api/v1/settings')
def settings(body:Preferences):
    for k,v in body.model_dump().items():store.set_setting(k,v)
    store.trim_cache(force=True);return body

from .api_more import router
app.include_router(router)
from . import photobook
app.include_router(photobook.router)

@app.get('/{path:path}')
def frontend(request:Request,path:str):
    root=store.PROJECT/'frontend'/'dist'
    file=store.confined(root,path,must_exist=False) if path else root/'index.html'
    if not file.is_file():file=root/'index.html'
    if not file.exists():return HTMLResponse('<h1>Build LiquidFrame first</h1><p>Run the setup script, then restart.</p>',503)
    response=FileResponse(file)
    if file.name=='index.html':response.set_cookie(session_cookie(request),SESSION,httponly=True,samesite='strict',max_age=86400)
    return response
