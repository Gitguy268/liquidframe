"""LiquidFrame domain routes; legacy endpoints stay available."""
from fastapi import APIRouter,Request,Response,UploadFile,File
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel,Field
import json,os,shutil,sqlite3,time
from . import store,catalog,jobs,media,workspaces,intelligence,deliveries
router=APIRouter(prefix='/api/v1')

@router.post('/query')
def query(body:dict):return catalog.query(body.get('query',body),body.get('offset',0),body.get('limit',120))
@router.post('/query/periods')
def periods(body:dict):return catalog.period_covers(body.get('query',{}),body.get('unit','month'))
@router.post('/query/selection')
def selection(body:dict):return catalog.snapshot(body.get('query',{}))
@router.post('/metadata')
def metadata(body:dict):return catalog.patch_assets(body.get('selection',{}),body.get('changes',{}),body.get('label','Change metadata'))
@router.post('/remove')
def remove(body:dict):return catalog.remove(body['selection'],body.get('permanent',False))
@router.post('/recover')
def recover(body:dict):return catalog.patch_assets(body['selection'],{'deleted_at':None,'purged':0},'Recover items')
@router.post('/history/undo')
def undo():return catalog.history_action()
@router.post('/history/redo')
def redo():return catalog.history_action(True)
@router.get('/history')
def history():return store.rows('SELECT id,label,undone,created FROM action_history ORDER BY created DESC LIMIT 100')
@router.get('/libraries')
def libraries():return workspaces.registry()
@router.post('/libraries')
def create_library(body:dict):return workspaces.add(body['name'],body['path'])
@router.post('/libraries/repair')
def repair():
    backup=store.data()/'backups'/f'catalog-repair-{int(time.time())}.sqlite3'
    with store.db() as c,sqlite3.connect(backup) as dest:c.backup(dest);result=c.execute('PRAGMA integrity_check').fetchone()[0]
    if result!='ok':raise ValueError('Catalog damage detected. Recovery copy saved; restore a verified catalog backup before rescanning.')
    store.execute('REINDEX');return {'integrity':result,'recovery_copy':backup.name}
@router.get('/private/status')
def private_status():return {'configured':bool(store.setting('private_passcode')),'unlocked':workspaces.PRIVATE.get()}
@router.post('/private/setup')
def private_setup(body:dict):workspaces.setup_passcode(body.get('passcode',''),body.get('old'));return {'configured':True}
@router.post('/private/unlock')
def unlock(body:dict,response:Response,request:Request):
    token=workspaces.unlock(body.get('passcode',''));response.set_cookie('liquidframe_private_'+str(request.url.port or 80),token,httponly=True,samesite='strict',max_age=86400);return {'unlocked':True,'expires_in':600}
@router.post('/private/lock')
def lock(request:Request,response:Response):
    key='liquidframe_private_'+str(request.url.port or 80);token=request.cookies.get(key)
    workspaces.SESSIONS.pop(token or '',None);response.delete_cookie(key);return {'unlocked':False}
@router.post('/private/renew')
def renew(request:Request):
    token=request.cookies.get('liquidframe_private_'+str(request.url.port or 80));ctx=workspaces.CURRENT.get()
    if not workspaces.private_unlocked(token,ctx.id):raise PermissionError('Private views are locked.')
    workspaces.SESSIONS[token]['until']=time.time()+600;return {'expires_in':600}
@router.get('/album-folders')
def folders():return store.rows('SELECT * FROM album_folders ORDER BY position,name')
@router.post('/album-folders')
def folder(body:dict):
    i=store.uid();store.execute('INSERT INTO album_folders(id,name,parent_id) VALUES(?,?,?)',(i,str(body['name'])[:150],body.get('parent_id')));return {'id':i}
@router.patch('/album-folders/{i}')
def move_folder(i:str,body:dict):
    if body.get('parent_id')==i:raise ValueError('A folder cannot contain itself.')
    parent=body.get('parent_id');seen={i}
    while parent:
        if parent in seen:raise ValueError('Folder nesting would create a cycle.')
        seen.add(parent);row=store.one('SELECT parent_id FROM album_folders WHERE id=?',(parent,));parent=row['parent_id'] if row else None
    store.execute('UPDATE album_folders SET name=COALESCE(?,name),parent_id=?,position=COALESCE(?,position) WHERE id=?',(body.get('name'),body.get('parent_id'),body.get('position'),i));return {'ok':True}
@router.delete('/album-folders/{i}')
def delete_folder(i:str):
    todo=[i]
    with store.db() as c:
        for folder_id in todo:
            todo.extend(r[0] for r in c.execute('SELECT id FROM album_folders WHERE parent_id=?',(folder_id,)))
            c.execute('DELETE FROM albums WHERE folder_id=?',(folder_id,));c.execute('DELETE FROM album_folders WHERE id=?',(folder_id,))
    return {'ok':True}
@router.post('/albums/create')
def album(body:dict):return catalog.create_album(body)
@router.patch('/albums/{i}/properties')
def album_properties(i:str,body:dict):
    allowed={'name','folder_id','cover_id','sort','position','rules'}
    if set(body)-allowed:raise ValueError('Unsupported album property.')
    if 'rules' in body:catalog.where(body['rules']);body['rules']=json.dumps(body['rules'])
    if body.get('cover_id'):store.get_asset(body['cover_id'])
    return catalog.album_mutation(i,body)
@router.post('/albums/{i}/selection')
def album_selection(i:str,body:dict):return catalog.album_items(i,body['selection'],body.get('remove',False))
@router.post('/albums/{i}/duplicate')
def duplicate_album(i:str):
    old=store.one('SELECT * FROM albums WHERE id=?',(i,))
    if not old:raise ValueError('Album not found.')
    result=catalog.create_album({'name':old['name']+' copy','folder_id':old['folder_id'],'kind':old['kind'],'rules':json.loads(old['rules'])})
    store.execute('INSERT INTO album_assets(album_id,asset_id,position) SELECT ?,asset_id,position FROM album_assets WHERE album_id=?',(result['id'],i));return result
@router.post('/albums/{i}/merge')
def merge_album(i:str,body:dict):
    target=body['target_id']
    if target==i:raise ValueError('Choose a different album.')
    if not store.one('SELECT id FROM albums WHERE id=?',(target,)):raise ValueError('Target album not found.')
    store.execute('INSERT OR IGNORE INTO album_assets(album_id,asset_id,position) SELECT ?,asset_id,position FROM album_assets WHERE album_id=?',(target,i));store.execute('DELETE FROM albums WHERE id=?',(i,));return {'ok':True}
@router.post('/albums/{i}/reorder')
def reorder(i:str,body:dict):
    with store.db() as c:
        for n,a in enumerate(body['ids']):c.execute('UPDATE album_assets SET position=? WHERE album_id=? AND asset_id=?',(n,i,a))
    return {'ok':True}
@router.post('/stacks')
def stack(body:dict):return catalog.stack(body['selection'],body.get('kind','manual'),body.get('primary_id'))
@router.get('/stacks/{i}')
def stack_items(i:str):return {'stack':store.one('SELECT * FROM stacks WHERE id=?',(i,)),'assets':[catalog.normalize(store.get_asset(a['id'])) for a in store.rows('SELECT id FROM assets WHERE stack_id=?',(i,))]}
@router.patch('/stacks/{i}')
def stack_primary(i:str,body:dict):
    a=store.get_asset(body['primary_id'])
    if a['stack_id']!=i:raise ValueError('Choose a component of this stack.')
    store.execute('UPDATE stacks SET primary_id=? WHERE id=?',(a['id'],i));return {'ok':True}
@router.delete('/stacks/{i}')
def unstack(i:str):
    for a in store.rows('SELECT id FROM assets WHERE stack_id=?',(i,)):store.get_asset(a['id'])
    store.execute('UPDATE assets SET stack_id=NULL WHERE stack_id=?',(i,));store.execute('DELETE FROM stacks WHERE id=?',(i,));return {'ok':True}
@router.post('/duplicates/merge')
def duplicate_merge(body:dict):return catalog.duplicate_merge(catalog.ids(body['selection']),body['winner'])
@router.post('/assets/{i}/viewed')
def viewed(i:str):store.get_asset(i);store.execute('UPDATE assets SET viewed_at=? WHERE id=?',(store.now(),i));return {'ok':True}
@router.post('/assets/{i}/relink')
def relink(i:str,body:dict):
    from . import library
    a=store.get_asset(i);p=Path(body['path']).expanduser().resolve(strict=True)
    if not p.is_file():raise ValueError('Choose a file.')
    root=library.add_root(str(p.parent));st=p.stat()
    if a['sha256'] and store.digest(p)!=a['sha256'] and not body.get('acknowledge_different'):raise ValueError('This is a different source. Confirm the relink explicitly.')
    store.execute('UPDATE assets SET root_id=?,relative_path=?,canonical_path=?,name=?,size=?,mtime_ns=?,revision=revision+1,status=\'ready\' WHERE id=?',(root['id'],p.name,str(p),p.name,st.st_size,st.st_mtime_ns,i));return {'ok':True}
@router.get('/media/{i}/source')
def source(i:str):
    a=store.get_asset(i);return FileResponse(store.asset_path(a),headers={'Cache-Control':'no-store'})
@router.get('/media/{i}/proxy')
def video_proxy(i:str):
    result=media.proxy(i)
    if result['ready']:return FileResponse(result['path'],media_type='video/mp4',headers={'Cache-Control':'no-store'})
    from fastapi.responses import JSONResponse
    return JSONResponse(result,202)
@router.get('/media/{i}/frame')
def video_frame(i:str,time:float=0,size:int=1600):
    a=store.get_asset(i);return FileResponse(media.frame(store.asset_path(a),time,min(2048,size)),media_type='image/png',headers={'Cache-Control':'no-store'})
@router.post('/media/{i}/export')
def video_export(i:str,body:dict):
    a=store.get_asset(i);store.asset_path(a,body['revision']);store.root_path(body['output_root']);return {'job_id':jobs.create('video_export',{'asset_id':i,**body})}
@router.post('/media/{i}/live-effect')
def effect(i:str,body:dict):
    store.get_asset(i)
    if body.get('effect') not in ['loop','bounce','long_exposure']:raise ValueError('Unknown Live Photo effect.')
    return {'job_id':jobs.create('live_effect',{'asset_id':i,**body})}
@router.get('/media/{i}/result/{name}')
def result(i:str,name:str,download:bool=False):
    store.get_asset(i)
    if store.setting('result-owner-'+name)!=i:raise PermissionError('This result belongs to another item.')
    if not name.startswith(tuple('0123456789abcdef')) or Path(name).suffix not in ['.tif','.mp4']:raise ValueError('Unknown result.')
    path=store.confined(store.data()/'results',name)
    if path.suffix=='.tif' and not download:
        from . import imaging
        rgb,alpha,_=imaging.render(path,preview=2048)
        return Response(imaging.display(rgb,alpha).write_to_buffer('.webp',Q=90),media_type='image/webp',headers={'Cache-Control':'no-store'})
    return FileResponse(path,filename=path.name if download else None,headers={'Cache-Control':'no-store'})
@router.get('/adapters')
def adapters():
    from . import native
    return {'tools':media.capabilities(),'native':native.capabilities()}
@router.get('/people/manage')
def people_manage():
    return catalog.people(include_hidden=True)
@router.patch('/people/{i}/properties')
def person_properties(i:str,body:dict):
    catalog.authorize_person(i)
    allowed={'name','favorite','hidden','feature_less','cover_id','position','group_id'}
    if not body or set(body)-allowed:raise ValueError('Invalid person properties.')
    if body.get('cover_id'):store.get_asset(body['cover_id'])
    store.execute('UPDATE people SET '+','.join(k+'=?' for k in body)+' WHERE id=?',[*body.values(),i]);return {'ok':True}
@router.post('/faces/{i}/reject')
def reject_face(i:str,body:dict):
    f=store.one('SELECT * FROM faces WHERE id=?',(i,));store.get_asset(f['asset_id'])
    store.execute('INSERT OR IGNORE INTO people_rejections VALUES(?,?)',(i,f['person_id']));store.execute('UPDATE faces SET rejected=1,confirmed=0 WHERE id=?',(i,));return {'ok':True}
@router.post('/faces/{i}/confirm')
def confirm_face(i:str):
    f=store.one('SELECT * FROM faces WHERE id=?',(i,));store.get_asset(f['asset_id']);store.execute('UPDATE faces SET confirmed=1,rejected=0 WHERE id=?',(i,));return {'ok':True}
@router.post('/imports/upload')
async def upload(files:list[UploadFile]=File(...)):
    from . import library
    managed=store.data()/'managed';managed.mkdir(exist_ok=True);root=library.add_root(str(managed),'export',managed=True)
    created=[]
    for file in files:
        name=Path(file.filename or 'import').name
        if name in ['.','..'] or name.startswith('.'):raise ValueError('Invalid import filename.')
        target=store.confined(managed,name,False);n=1
        while target.exists():target=store.confined(managed,Path(name).stem+f'-{n}'+Path(name).suffix,False);n+=1
        temp=managed/('.'+store.uid()+'.upload');size=0
        try:
            with temp.open('xb') as out:
                while chunk:=await file.read(1024*1024):
                    size+=len(chunk)
                    if size>50*1024**3:raise ValueError('Import exceeds the 50 GB per-file limit.')
                    out.write(chunk)
            os.replace(temp,target);created.append(target.name)
        finally:temp.unlink(missing_ok=True);await file.close()
    return {'files':created,'job_id':jobs.create('scan',{'root_id':root['id']})}
@router.get('/imports')
def imports():return store.rows('SELECT i.*,COUNT(a.id) count FROM imports i JOIN assets a ON a.import_id=i.id WHERE '+catalog.visibility(alias='a')+' GROUP BY i.id ORDER BY i.created DESC')

@router.get('/looks')
def looks():
    from .adjustments import LOOKS
    return [{'name':k,'adjustments':v} for k,v in LOOKS.items()]
@router.post('/assets/{i}/straighten')
def straighten(i:str):
    from .adjustments import auto_straighten
    a=store.get_asset(i);return {'straighten':auto_straighten(store.asset_path(a))}
@router.post('/edits/paste')
def paste_edits(body:dict):
    chosen=catalog.ids(body['selection']);source=body['recipe'];groups=body.get('groups',['adjustments','raw'])
    for i in chosen:
        a=store.get_asset(i);current=store.get_recipe(i);recipe=current['recipe'].copy()
        for group in groups:
            if group not in ['adjustments','raw']:raise ValueError('Only portable adjustment groups can be pasted.')
            if group in source:recipe[group]=source[group]
        store.save_recipe(i,recipe,current['version'])
    return {'updated':len(chosen)}

@router.get('/devices')
def devices():
    from . import native
    return native.devices()
@router.post('/native/mac/{command}')
def mac_bridge(command:str,body:dict):
    from . import native
    if command not in ['authorize','albums','items','import','depth','depth-info','cinematic-info']:raise ValueError('Unknown adapter command.')
    if command in ['depth','depth-info','cinematic-info']:
        a=store.get_asset(body['asset_id']);body={**body,'path':str(store.asset_path(a))}
        if command=='depth':
            name=store.uid()+'.tif';body['output']=str(store.data()/'results'/name);result=native.bridge(command,body);store.set_setting('result-owner-'+name,a['id']);return {**result,'result':name}
    if command=='import':
        folder=store.data()/'managed'/('photos-'+store.uid());body={**body,'destination':str(folder)}
        result=native.bridge(command,body)
        from . import library
        root=library.add_root(str(folder),managed=True);result['job_id']=jobs.create('scan',{'root_id':root['id']});return result
    return native.bridge(command,body)

@router.post('/query/neighbors')
def neighbors(body:dict):
    q=catalog.prepare_query(body.get('query',{}));clause,args=catalog.where(q);order,orderargs=catalog.query_order(q)
    row=store.one('SELECT position FROM (SELECT id,ROW_NUMBER() OVER(ORDER BY '+order+')-1 position FROM assets WHERE '+clause+') WHERE id=?',[*orderargs,*args,body['asset_id']])
    if not row:return {'assets':[]}
    return catalog.query(q,max(0,row['position']-20),41)

@router.get('/assets/{i}/ocr')
def ocr(i:str):
    from .intelligence import ocr as recognize
    return recognize(store.get_asset(i))
@router.post('/analysis/extended')
def extended_analysis(body:dict):
    from . import intelligence
    allowed={'semantic','people','duplicates','ocr','pets','curation','video'}
    if set(body.get('kinds',[]))-allowed:raise ValueError('Unknown analysis kind.')
    return {'job_id':jobs.create('extended_analysis',body)}
@router.get('/search/suggest')
def suggest(q:str=''):
    from .intelligence import suggestions
    return suggestions(q)
@router.get('/collections')
def collections(kind:str='memories'):
    result=[]
    for c in store.rows('SELECT * FROM collections WHERE kind=?',(kind,)):
        ids=json.loads(c['assets']);visible=[]
        for i in ids:
            if store.one('SELECT id FROM assets WHERE id=? AND '+catalog.visibility(),(i,)):visible.append(i)
        if visible:c['assets']=visible;c['count']=len(visible);c['cover']=visible[0];result.append(c)
    return result
@router.patch('/collections/{i}')
def collection_update(i:str,body:dict):
    allowed={'name','hidden','featured','assets'}
    if not body or set(body)-allowed:raise ValueError('Unsupported collection property.')
    if 'assets' in body:
        for asset_id in body['assets']:store.get_asset(asset_id)
        body['assets']=json.dumps(body['assets'])
    store.execute('UPDATE collections SET '+','.join(k+'=?' for k in body)+' WHERE id=?',[*body.values(),i]);return {'ok':True}
@router.get('/places/points')
def points():
    rows=store.rows('SELECT id,title,name,latitude,longitude FROM assets WHERE '+catalog.visibility()+' AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180 LIMIT 100000')
    return {'type':'FeatureCollection','features':[{'type':'Feature','geometry':{'type':'Point','coordinates':[r['longitude'],r['latitude']]},'properties':{'id':r['id'],'title':r['title'] or r['name']}} for r in rows]}
@router.post('/places/region')
def region(body:dict):
    rows=store.rows('SELECT * FROM assets WHERE '+catalog.visibility()+' AND latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ? LIMIT 240',(body['south'],body['north'],body['west'],body['east']))
    return {'assets':[catalog.normalize(a) for a in rows]}
@router.get('/places/search')
def places_search(q:str=''):
    path=store.PROJECT/'frontend/public/maps/cities.json'
    if not path.exists():return []
    return [c for c in json.loads(path.read_text()) if q.casefold() in c['name'].casefold()][:20] if q.strip() else []
@router.post('/media/{i}/preview')
def video_preview(i:str,body:dict):
    from . import imaging
    a=store.get_asset(i);path=store.asset_path(a);frame=media.frame(path,body.get('time',0),min(2048,int(body.get('size',1200))));rgb,alpha,_=imaging.render(frame,body.get('recipe',{}));data=imaging.display(rgb,alpha).write_to_buffer('.png')
    from fastapi.responses import Response
    return Response(data,media_type='image/png',headers={'Cache-Control':'no-store'})

@router.post('/batch/export')
def batch_export(body:dict):
    from . import deliveries
    store.root_path(body['output_root'])
    from .schemas import Options
    options=body.get('options',{})
    validated=Options.model_validate({k:v for k,v in options.items() if k in Options.model_fields}).model_dump(exclude_none=True)
    body['options']={**options,**validated}
    chosen=catalog.ids(body['selection']);body['revisions']={}
    for i in chosen:
        a=store.get_asset(i);body['revisions'][i]=a['revision']
        if body.get('mode')!='original' and int(a['metadata'].get('pages',1))>1 and not options.get('preserve_frames') and not body.get('acknowledge_flatten'):
            raise ValueError('This selection includes animation or multiple pages. Preserve frames or acknowledge exporting a single frame.')
    if body.get('mode')!='original' and not options.get('location',True) and options.get('metadata',True) and not media.executable('exiftool'):
        raise ValueError('Removing location while keeping other metadata requires ExifTool. Install it or disable all metadata.')
    return {'job_id':jobs.create('batch_export',body)}
@router.get('/projects')
def projects():
    from .deliveries import project_allowed
    result=[]
    for p in store.rows('SELECT * FROM projects ORDER BY updated DESC'):
        try:p['document']=project_allowed(p);result.append(p)
        except PermissionError:continue
    return result
@router.post('/projects')
def create_project(body:dict):
    from .deliveries import create_project
    return create_project(body['name'],body.get('kind','slideshow'),body.get('selection',{}))
@router.get('/projects/{i}')
def get_project(i:str):
    from .deliveries import project_allowed
    p=store.one('SELECT * FROM projects WHERE id=?',(i,))
    if not p:raise ValueError('Project not found.')
    p['document']=project_allowed(p);p['assets']=[catalog.normalize(store.get_asset(a)) for a in p['document'].get('asset_ids',[])];return p
@router.put('/projects/{i}')
def update_project(i:str,body:dict):
    from .deliveries import project_allowed
    old=store.one('SELECT * FROM projects WHERE id=?',(i,));project_allowed(old);doc=body['document']
    if len(doc.get('asset_ids',[]))>500:raise ValueError('Projects support up to 500 items.')
    for a in doc.get('asset_ids',[]):store.get_asset(a)
    store.execute('UPDATE projects SET name=?,document=?,updated=? WHERE id=?',(body['name'][:150],json.dumps(doc),store.now(),i));return {'ok':True}
@router.delete('/projects/{i}')
def delete_project(i:str):
    from .deliveries import project_allowed
    p=store.one('SELECT * FROM projects WHERE id=?',(i,));project_allowed(p);store.execute('DELETE FROM projects WHERE id=?',(i,));return {'ok':True}
@router.post('/projects/{i}/export')
def export_project(i:str,body:dict):
    from .deliveries import project_allowed
    project_allowed(store.one('SELECT * FROM projects WHERE id=?',(i,)));store.root_path(body['output_root']);return {'job_id':jobs.create('project_export',{'project_id':i,**body})}
@router.post('/print')
def print_selection(body:dict):
    from .deliveries import print_pdf
    ids=catalog.ids(body['selection'])
    for i in ids:store.get_asset(i)
    uid=print_pdf(body['selection'],body);store.set_setting('print-'+uid,ids);return {'id':uid}
@router.get('/print/{i}')
def print_result(i:str):
    for asset_id in store.setting('print-'+i,[]):store.get_asset(asset_id)
    if not store.setting('print-'+i):raise ValueError('Print document not found.')
    return FileResponse(store.confined(store.data()/'results',i+'.pdf'),media_type='application/pdf',headers={'Cache-Control':'no-store'})

@router.get('/assets/{i}/look-preview')
def look_preview(i:str,look:str='Original'):
    from . import imaging
    from .adjustments import LOOKS
    a=store.get_asset(i);rgb,alpha,_=imaging.render(store.asset_path(a),{'adjustments':LOOKS.get(look,{})},preview=160)
    return Response(imaging.display(rgb,alpha).write_to_buffer('.webp'),media_type='image/webp',headers={'Cache-Control':'no-store'})

@router.post('/metadata/shift-time')
def shift_time(body:dict):
    import datetime
    seconds=float(body['seconds'])
    if abs(seconds)>31557600000:raise ValueError('Time correction is too large.')
    before=[];after=[]
    with store.db() as c:
        for i in catalog.ids(body['selection']):
            a=store.get_asset(i);date=datetime.datetime.fromisoformat(a['captured'].replace('Z','+00:00'));value=(date+datetime.timedelta(seconds=seconds)).isoformat()
            before.append({'table':'assets','id':i,'values':{'captured':a['captured']}});after.append({'table':'assets','id':i,'values':{'captured':value}});c.execute('UPDATE assets SET captured=? WHERE id=?',(value,i))
        catalog.journal('Adjust capture times',before,after,c)
    return {'updated':len(after)}
@router.post('/assets/{i}/consolidate')
def consolidate(i:str):
    from . import library
    a=store.get_asset(i);source=store.asset_path(a);managed=store.data()/'managed';managed.mkdir(exist_ok=True);root=library.add_root(str(managed),'export',managed=True);out=store.confined(managed,source.name,False);n=1
    while out.exists():out=store.confined(managed,source.stem+f'-{n}'+source.suffix,False);n+=1
    temp=out.with_name('.'+store.uid()+'.copy')
    try:
        original=store.digest(source);shutil.copy2(source,temp)
        if store.digest(temp)!=original or store.digest(source)!=original:raise ValueError('Source copy did not verify.')
        os.replace(temp,out);st=out.stat();store.execute('UPDATE assets SET canonical_path=?,root_id=?,relative_path=?,mtime_ns=? WHERE id=?',(str(out),root['id'],out.name,st.st_mtime_ns,i))
    finally:temp.unlink(missing_ok=True)
    return {'managed':True}
@router.post('/media/{i}/poster')
def poster(i:str,body:dict):
    a=store.get_asset(i);seconds=max(0,min(a['duration'],float(body['time'])));store.set_setting('poster-'+i,seconds);store.execute('UPDATE assets SET edited_at=? WHERE id=?',(store.now(),i));return {'time':seconds}
@router.post('/media/{i}/extract-frame')
def extract_frame(i:str,body:dict):
    from . import library,imaging
    a=store.get_asset(i);path=store.asset_path(a);root=store.root_path(body['output_root']);out=store.confined(root,Path(a['name']).stem+'-frame-'+store.uid()[:6]+'.png',False)
    frame=media.frame(path,float(body.get('time',0)),4000);imaging.encode(frame,body.get('recipe',{}),{'format':'png'},out);return {'path':str(out)}

@router.get('/navigation')
def navigation():return store.setting('navigation',{'pins':[]})
@router.put('/navigation')
def navigation_update(body:dict):
    if len(body.get('pins',[]))>100:raise ValueError('Pin at most 100 collections.')
    for pin in body.get('pins',[]):
        catalog.where(pin.get('query',{}));pin['label']=str(pin['label'])[:150]
    store.set_setting('navigation',body);return body
@router.get('/keywords')
def keywords():
    return {'keywords':store.rows('SELECT j.value keyword,COUNT(*) count FROM assets a,json_each(a.keywords) j WHERE '+catalog.visibility(alias='a')+' GROUP BY j.value ORDER BY j.value COLLATE NOCASE'),'preferences':store.setting('keyword_preferences',{})}
@router.post('/keywords/rename')
def rename_keyword(body:dict):
    old=str(body['old']);new=str(body.get('new','')).strip()[:150];before=[];after=[]
    with store.db() as c:
        rows=c.execute('SELECT id,keywords FROM assets WHERE '+catalog.visibility()+" AND keywords LIKE ?",('%'+old+'%',)).fetchall()
        for r in rows:
            keys=json.loads(r['keywords'])
            if old not in keys:continue
            keys=list(dict.fromkeys((new if k==old else k) for k in keys if k!=old or new));value=json.dumps(keys)
            before.append({'table':'assets','id':r['id'],'values':{'keywords':r['keywords']}});after.append({'table':'assets','id':r['id'],'values':{'keywords':value}});c.execute('UPDATE assets SET keywords=? WHERE id=?',(value,r['id']))
        catalog.journal('Rename keyword' if new else 'Remove keyword',before,after,c)
    return {'updated':len(after)}
@router.put('/keywords/preferences')
def keyword_preferences(body:dict):
    if len(json.dumps(body))>10000:raise ValueError('Keyword preferences are too large.')
    store.set_setting('keyword_preferences',body);return body
@router.post('/albums/{i}/move-item')
def move_album_item(i:str,body:dict):
    asset=store.get_asset(body['asset_id']);target=store.get_asset(body['before_id'])
    with store.db() as c:
        old=c.execute('SELECT position FROM album_assets WHERE album_id=? AND asset_id=?',(i,asset['id'])).fetchone();position=c.execute('SELECT position FROM album_assets WHERE album_id=? AND asset_id=?',(i,target['id'])).fetchone()
        if not old or not position:raise ValueError('Both items must be in this album.')
        lower=c.execute('SELECT MAX(position) FROM album_assets WHERE album_id=? AND position<?',(i,position[0])).fetchone()[0];new=(position[0]+lower)/2 if lower is not None else position[0]-1
        c.execute('UPDATE album_assets SET position=? WHERE album_id=? AND asset_id=?',(new,i,asset['id']));catalog.journal('Reorder album',[catalog.row_change('album_assets',{'album_id':i,'asset_id':asset['id']},{'position':old[0],'album_id':i,'asset_id':asset['id']})],[catalog.row_change('album_assets',{'album_id':i,'asset_id':asset['id']},{'position':new,'album_id':i,'asset_id':asset['id']})],c)
    return {'ok':True}
@router.put('/period-cover')
def period_cover(body:dict):
    a=store.get_asset(body['asset_id']);unit=body.get('unit','month')
    if unit not in ['month','year']:raise ValueError('Unknown time period.')
    key=unit+':'+a['captured'][:4 if unit=='year' else 7];overrides=store.setting('period_covers',{});overrides[key]=a['id'];store.set_setting('period_covers',overrides);return {'ok':True}
@router.post('/metadata/keyword')
def apply_keyword(body:dict):
    updated=0
    for i in catalog.ids(body['selection']):
        a=store.get_asset(i);keys=list(dict.fromkeys([*a['keywords'],str(body['keyword'])[:150]]));catalog.patch_assets([i],{'keywords':keys},'Add keyword');updated+=1
    return {'updated':updated}

@router.post('/assets/{i}/faces/manual')
def manual_face(i:str,body:dict):
    import numpy as np
    a=store.get_asset(i);box=body['box']
    if len(box)!=4 or any(not 0<=float(v)<=1 for v in box) or box[2]<=0 or box[3]<=0 or box[0]+box[2]>1 or box[1]+box[3]>1:raise ValueError('Choose a box inside the photo.')
    person=body.get('person_id')
    if person:catalog.authorize_person(person)
    if not person:person=store.uid();store.execute('INSERT INTO people(id,name,created) VALUES(?,?,?)',(person,body.get('name','Unnamed person')[:150],store.now()))
    face=store.uid();store.execute('INSERT INTO faces(id,asset_id,revision,person_id,box,vector,confirmed) VALUES(?,?,?,?,?,?,1)',(face,i,a['revision'],person,json.dumps(box),np.zeros(128,np.float32).tobytes()));return {'id':face,'person_id':person}
@router.get('/assets/{i}/observations')
def observations(i:str):
    store.get_asset(i);rows=store.rows('SELECT id,label,box,person_id,kind,timestamp FROM observations WHERE asset_id=?',(i,))
    for r in rows:r['box']=json.loads(r['box'])
    return rows
@router.patch('/observations/{i}')
def correct_observation(i:str,body:dict):
    row=store.one('SELECT * FROM observations WHERE id=?',(i,))
    if not row:raise ValueError('Suggestion not found.')
    store.get_asset(row['asset_id']);person=body.get('person_id')
    if body.get('reject'):store.execute('UPDATE observations SET person_id=NULL,kind=\'rejected\' WHERE id=?',(i,));return {'ok':True}
    if not person:
        person=store.uid();store.execute('INSERT INTO people(id,name,created,kind) VALUES(?,?,?,?)',(person,body.get('name','Unnamed pet')[:150],store.now(),'pet'))
    catalog.authorize_person(person)
    store.execute('UPDATE observations SET person_id=? WHERE id=?',(person,i));return {'ok':True}
@router.post('/collections/{i}/split')
def split_collection(i:str,body:dict):
    old=store.one('SELECT * FROM collections WHERE id=?',(i,));chosen=set(catalog.ids(body['selection']));members=json.loads(old['assets'])
    for a in members:store.get_asset(a)
    kept=[a for a in members if a not in chosen];moved=[a for a in members if a in chosen]
    if not kept or not moved:raise ValueError('Choose some, but not all, items in this moment.')
    new=store.uid()
    with store.db() as c:c.execute('UPDATE collections SET assets=? WHERE id=?',(json.dumps(kept),i));c.execute('INSERT INTO collections(id,kind,name,assets,created) VALUES(?,?,?,?,?)',(new,old['kind'],str(body.get('name',old['name']+' — split'))[:150],json.dumps(moved),store.now()))
    return {'id':new}
@router.post('/collections/{i}/merge')
def merge_collection(i:str,body:dict):
    old=store.one('SELECT * FROM collections WHERE id=?',(i,));target=store.one('SELECT * FROM collections WHERE id=?',(body['target_id'],))
    if not old or not target or i==target['id']:raise ValueError('Choose two different collections.')
    members=list(dict.fromkeys([*json.loads(target['assets']),*json.loads(old['assets'])]))
    for a in members:store.get_asset(a)
    with store.db() as c:c.execute('UPDATE collections SET assets=? WHERE id=?',(json.dumps(members),target['id']));c.execute('DELETE FROM collections WHERE id=?',(i,))
    return {'id':target['id']}
