from __future__ import annotations
import json, os, shutil
from pathlib import Path
from . import store, imaging, jobs


def atomic_copy(source,destination):
    tmp=destination.with_name('.'+destination.name+'.'+store.uid()+'.tmp')
    try:
        with source.open('rb') as src,tmp.open('xb') as out:
            shutil.copyfileobj(src,out,1024*1024);out.flush();os.fsync(out.fileno())
        if store.digest(tmp)!=store.digest(source):raise ValueError('Backup verification failed.')
        os.replace(tmp,destination)
    finally:tmp.unlink(missing_ok=True)

@jobs.register('export')
def export(payload,ctx):
    output_root=store.root_path(payload['output_root']) if not payload.get('replace') else None
    assets=payload['assets']; results=[];errors=[]
    persistent=bool(store.one('SELECT id FROM jobs WHERE id=?',(ctx.id,)))
    previous=store.rows('SELECT asset_id,path,backup_id FROM export_items WHERE job_id=? AND error IS NULL',(ctx.id,)) if persistent else []
    done={p['asset_id'] for p in previous};results.extend(previous[:200]);file_count=len(done);error_count=0
    for n,item in enumerate(assets):
        if item['id'] in done:continue
        ctx.progress(n/max(len(assets),1),f'Exporting {n+1}/{len(assets)}')
        temp=None
        try:
            a=store.get_asset(item['id']);path=store.asset_path(a,item['revision'])
            recipe=item.get('recipe') if 'recipe' in item else store.get_recipe(a['id'])['recipe']
            options=payload['options'];fmt=options.get('format','jpg').lower();fmt={'jpeg':'jpg','tiff':'tif'}.get(fmt,fmt)
            if a['metadata'].get('pages',1)>1 and not options.get('preserve_frames') and not payload.get('acknowledge_flatten'):
                raise ValueError('This file has multiple frames/pages. Acknowledge flattening or preserve them.')
            if payload.get('replace'):
                if path.suffix[1:].lower() not in {fmt,'jpeg' if fmt=='jpg' else fmt,'tiff' if fmt=='tif' else fmt}:raise ValueError('Replacing an original must keep its format. Export a new copy to convert.')
                if path.suffix[1:].lower() in imaging.RAW:raise ValueError('RAW originals cannot be replaced with developed pixels. Export a new copy.')
                target=path
            else:
                relative=Path(a['relative_path']).parent/(Path(a['name']).stem+'-edited.'+fmt)
                target=store.confined(output_root,str(relative),must_exist=False);target.parent.mkdir(parents=True,exist_ok=True)
                serial=1
                while target.exists():
                    target=store.confined(output_root,str(relative.with_name(relative.stem+f'-{serial}'+relative.suffix)),must_exist=False);serial+=1
            temp=target.with_name('.'+target.stem+'.'+store.uid()+'.'+fmt)
            imaging.encode(path,recipe,options,temp);ctx.check();store.asset_path(a,item['revision'])
            backup_id=None
            if payload.get('replace'):
                backup_id=store.uid();backup=store.data()/'backups'/(backup_id+path.suffix)
                original_hash=store.digest(path)
                atomic_copy(path,backup)
                if store.digest(backup)!=original_hash:raise ValueError('Backup failed. Original was not replaced.')
                store.asset_path(a,item['revision'])
                if store.digest(path)!=original_hash:raise ValueError('Original changed during export. Replacement cancelled.')
                store.execute('INSERT INTO backups VALUES(?,?,?,?,?,?,0)',(backup_id,a['id'],str(backup),original_hash,store.digest(temp),store.now()))
            ctx.check();os.replace(temp,target);temp=None
            if payload.get('replace'):
                store.update_source(a['id']);store.save_recipe(a['id'],{},store.get_recipe(a['id'])['version'])
            if persistent:store.execute('INSERT OR REPLACE INTO export_items VALUES(?,?,?,?,NULL)',(ctx.id,a['id'],str(target),backup_id))
            if len(results)<200:results.append({'asset_id':a['id'],'path':str(target),'backup_id':backup_id})
            file_count+=1
        except jobs.Cancelled:raise
        except Exception as e:
            error_count+=1
            if len(errors)<100:errors.append({'asset_id':item['id'],'error':str(e)})
            if persistent:store.execute('INSERT OR REPLACE INTO export_items VALUES(?,?,NULL,NULL,?)',(ctx.id,item['id'],str(e)))
        finally:
            if temp:temp.unlink(missing_ok=True)
    if errors and not results:raise ValueError('\n'.join(e['error'] for e in errors[:5]))
    return {'files':results,'errors':errors,'file_count':file_count,'error_count':error_count}

@jobs.register('restore')
def restore(payload,ctx):
    b=store.one('SELECT * FROM backups WHERE id=?',(payload['backup_id'],))
    if not b or b['restored']:raise ValueError('Backup is not available for restoration.')
    a=store.get_asset(b['asset_id']);path=store.asset_path(a,check_stat=False)
    backup=store.confined(store.data()/'backups',Path(b['path']).name)
    if store.digest(backup)!=b['original_sha']:raise ValueError('Backup is damaged; current photo was not changed.')
    if store.digest(path)!=b['output_sha']:raise ValueError('Photo changed since replacement. Export the backup to a new file instead.')
    ctx.progress(.2,'Preserving the current photo…')
    current=store.data()/'backups'/(store.uid()+path.suffix);atomic_copy(path,current)
    ctx.check();atomic_copy(backup,path)
    store.execute('UPDATE backups SET restored=1 WHERE id=?',(b['id'],));store.update_source(a['id'])
    return {'asset_id':a['id'],'path':str(path),'previous_version':str(current)}
