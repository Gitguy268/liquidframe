from __future__ import annotations
import datetime, json, os, threading, time, contextvars
from pathlib import Path
import cv2
import numpy as np
from . import store, imaging, jobs, models, media

SCAN_LOCKS={}; WATCHER=None
WATCH_STOP=threading.Event();WATCH_REQUEST=threading.Event();WATCH_THREAD=None

def add_root(path,kind='library',managed=False):
    p=Path(path).expanduser().resolve(strict=True)
    if not p.is_dir(): raise ValueError('Select a folder.')
    if (p==store.data() or p.is_relative_to(store.data())) and not (managed and p.is_relative_to(store.data()/'managed')): raise ValueError('The app data folder cannot be a photo library.')
    root=store.one('SELECT * FROM roots WHERE path=?',(str(p),))
    if root:
        if root['kind']=='detached' or (kind=='library' and root['kind']=='export'): store.execute('UPDATE roots SET kind=? WHERE id=?',(kind,root['id']));root['kind']=kind
        return root
    i=store.uid(); store.execute('INSERT INTO roots VALUES(?,?,?,?,?)',(i,str(p),p.name or str(p),kind,store.now()))
    return store.one('SELECT * FROM roots WHERE id=?',(i,))

def walk(root):
    from .media import VIDEO
    extensions=imaging.accepted()|VIDEO
    for folder,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=[d for d in dirs if not d.startswith('.') and not (Path(folder)/d).is_symlink() and (Path(folder)/d).resolve()!=store.PROJECT]
        for name in files:
            path=Path(folder)/name
            if not name.startswith('.') and not path.is_symlink() and path.suffix[1:].lower() in extensions: yield path

@jobs.register('scan')
def scan(payload,ctx):
    root=store.root_path(payload['root_id'])
    lock=SCAN_LOCKS.setdefault(payload['root_id'],threading.Lock())
    with lock:
        count=0; errors=0;seen=set()
        import_id=store.uid();store.execute('INSERT INTO imports VALUES(?,?,?,?)',(import_id,payload['root_id'],store.now(),root.name))
        for path in walk(root):
            ctx.check();relative=str(path.relative_to(root))
            try:stat=path.stat()
            except OSError:errors+=1;continue
            old=store.one('SELECT * FROM assets WHERE canonical_path=?',(str(path),))
            if old and (old['root_id']!=payload['root_id']): continue
            i=old['id'] if old else store.uid();seen.add(i);count+=1
            if old and old['size']==stat.st_size and old['mtime_ns']==stat.st_mtime_ns and old['status']!='error':
                if old['status']=='missing': store.execute("UPDATE assets SET status='ready' WHERE id=?",(i,))
                continue
            try: width,height,bits,metadata,captured=imaging.metadata(path);status='ready';error=None
            except Exception as e: width=height=0;bits=8;metadata={};captured=None;status='error';error=str(e);errors+=1
            captured=captured or datetime.datetime.fromtimestamp(stat.st_mtime).isoformat()
            if old:
                store.execute('UPDATE assets SET relative_path=?,name=?,extension=?,size=?,mtime_ns=?,width=?,height=?,bits=?,captured=?,metadata=?,status=?,error=?,revision=revision+1,sha256=NULL,phash=NULL WHERE id=?',(relative,path.name,path.suffix[1:].lower(),stat.st_size,stat.st_mtime_ns,width,height,bits,old['captured'] if 'captured' in json.loads(old.get('user_meta') or '{}').get('overrides',{}) else captured,json.dumps(metadata),status,error,i))
                store.execute('DELETE FROM embeddings WHERE asset_id=?',(i,));store.execute('DELETE FROM faces WHERE asset_id=?',(i,))
            else:
                store.execute('INSERT INTO assets(id,root_id,relative_path,canonical_path,name,extension,size,mtime_ns,width,height,bits,captured,metadata,status,error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(i,payload['root_id'],relative,str(path),path.name,path.suffix[1:].lower(),stat.st_size,stat.st_mtime_ns,width,height,bits,captured,json.dumps(metadata),status,error))
            from . import media,metadata_tools
            kind='video' if path.suffix[1:].lower() in media.VIDEO else 'photo'
            store.execute('UPDATE assets SET media_kind=?,duration=?,import_id=COALESCE(import_id,?),imported_at=COALESCE(imported_at,?) WHERE id=?',(kind,float(metadata.get('duration',0)),import_id,store.now(),i))
            metadata_tools.enrich(i,path,metadata)
            if count%10==0: ctx.progress(min(.95,count/(count+100)),f'Indexed {count:,} media items')
        for a in store.rows('SELECT id FROM assets WHERE root_id=?',(payload['root_id'],)):
            if a['id'] not in seen: store.execute("UPDATE assets SET status='missing' WHERE id=?",(a['id'],))
        from .metadata_tools import associate
        associate(payload['root_id'])
        return {'photos':count,'errors':errors,'root_id':payload['root_id']}

def phash(a):
    g=cv2.cvtColor(cv2.resize(a,(32,32)),cv2.COLOR_RGB2GRAY).astype(np.float32)
    d=cv2.dct(g)[:8,:8];bits=d>np.median(d.flatten()[1:]);bits[0,0]=False
    return f'{sum(int(b)<<i for i,b in enumerate(bits.flatten())):016x}'

@jobs.register('analysis')
def analyze(payload,ctx):
    kinds=payload.get('kinds',['duplicates'])
    for i,key in enumerate(kinds):
        if key!='duplicates': models.ensure('semantic' if key=='semantic' else 'people',ctx,i*.1,.1)
    with store.db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS analysis_state(asset_id TEXT,kind TEXT,revision INTEGER,PRIMARY KEY(asset_id,kind))')
    from .catalog import visibility
    where="a.status='ready' AND "+visibility(alias='a');args=[]
    if payload.get('root_id'):where+=' AND a.root_id=?';args.append(payload['root_id'])
    total=store.one('SELECT COUNT(*) n FROM assets a WHERE '+where,args)['n']; processed=0;errors=[]
    offset=0
    while True:
        assets=store.rows('SELECT a.* FROM assets a WHERE '+where+' ORDER BY a.id LIMIT 100 OFFSET ?',[*args,offset])
        if not assets:break
        for a in assets:
            ctx.progress(.3+.65*processed/max(total,1),f'Analyzing {processed+1:,}/{total:,} items')
            processed+=1
            try:
                path=store.asset_path(a)
                needed=[k for k in kinds if not store.one('SELECT asset_id FROM analysis_state WHERE asset_id=? AND kind=? AND revision=?',(a['id'],k,a['revision']))]
                if not needed: continue
                rgb,_,_=imaging.render(path,{},preview=1024);pixels=imaging.array(rgb)
                if 'duplicates' in needed:
                    store.execute('UPDATE assets SET sha256=?,phash=? WHERE id=? AND revision=?',(store.digest(path),phash(pixels),a['id'],a['revision']))
                if 'semantic' in needed:
                    vector=models.image_embedding(pixels)
                    store.execute('INSERT OR REPLACE INTO embeddings VALUES(?,?,?)',(a['id'],a['revision'],vector.tobytes()))
                if 'people' in needed:
                    found=models.faces(pixels);store.execute('DELETE FROM faces WHERE asset_id=?',(a['id'],))
                    # Conservative automatic grouping; manual assignments persist until the source changes.
                    reps=store.rows('SELECT person_id,vector FROM faces GROUP BY person_id')
                    for box,vector in found:
                        best=None;score=.55
                        for rep in reps:
                            sim=float(np.dot(vector,np.frombuffer(rep['vector'],np.float32)))
                            if sim>score:best=rep['person_id'];score=sim
                        if not best:
                            best=store.uid();store.execute('INSERT INTO people(id,name,created) VALUES(?,?,?)',(best,'Unnamed person',store.now()));reps.append({'person_id':best,'vector':vector.tobytes()})
                        store.execute('INSERT INTO faces(id,asset_id,revision,person_id,box,vector) VALUES(?,?,?,?,?,?)',(store.uid(),a['id'],a['revision'],best,json.dumps(box),vector.tobytes()))
                store.asset_path(a)
                for key in needed: store.execute('INSERT OR REPLACE INTO analysis_state VALUES(?,?,?)',(a['id'],key,a['revision']))
            except jobs.Cancelled:raise
            except Exception as e:errors.append({'asset_id':a['id'],'error':str(e)})
        offset+=len(assets)
    return {'processed':processed,'errors':errors[:100],'error_count':len(errors)}

def semantic_search(text,limit=500):
    if not models.installed('semantic'): raise ValueError('Download the semantic search model and run library analysis first.')
    query=models.text_embedding(text);top=[]
    # Stream embeddings in batches instead of constructing a 100,000-photo matrix.
    with store.db() as c:
        cursor=c.execute('SELECT e.asset_id,e.vector FROM embeddings e JOIN assets a ON a.id=e.asset_id AND a.revision=e.revision WHERE a.status="ready" AND a.hidden=0 AND a.deleted_at IS NULL AND a.purged=0')
        while batch:=cursor.fetchmany(1000):
            scores=np.vstack([np.frombuffer(r['vector'],np.float32) for r in batch])@query
            top.extend((float(s),r['asset_id']) for s,r in zip(scores,batch))
            top=sorted(top,reverse=True)[:limit]
    best={i:{'id':i,'score':s} for s,i in top}
    with store.db() as c:
        cursor=c.execute('SELECT f.asset_id,f.timestamp AS time,f.vector FROM frame_search f JOIN assets a ON a.id=f.asset_id AND a.revision=f.revision WHERE a.status="ready" AND a.hidden=0 AND a.deleted_at IS NULL AND a.purged=0')
        while batch:=cursor.fetchmany(1000):
            scores=np.vstack([np.frombuffer(r['vector'],np.float32) for r in batch])@query
            for score,r in zip(scores,batch):
                if r['asset_id'] not in best or score>best[r['asset_id']]['score']:best[r['asset_id']]={'id':r['asset_id'],'score':float(score),'match_time':r['time']}
            best={r['id']:r for r in sorted(best.values(),key=lambda r:r['score'],reverse=True)[:limit]}
    return sorted(best.values(),key=lambda r:r['score'],reverse=True)[:limit]

class BKTree:
    def __init__(self):self.root=None
    def insert(self,value,item):
        if self.root is None:self.root=[value,[item],{}];return
        node=self.root
        while True:
            d=(value^node[0]).bit_count()
            if not d:node[1].append(item);return
            if d not in node[2]:node[2][d]=[value,[item],{}];return
            node=node[2][d]
    def query(self,value,radius=6):
        result=[];stack=[self.root] if self.root else []
        while stack:
            n=stack.pop();d=(value^n[0]).bit_count()
            if d<=radius:result.extend(n[1])
            stack.extend(v for k,v in n[2].items() if d-radius<=k<=d+radius)
        return result

def duplicates():
    assets=store.rows("SELECT id,name,sha256,phash FROM assets WHERE status='ready' AND hidden=0 AND deleted_at IS NULL AND purged=0 AND phash IS NOT NULL")
    tree=BKTree();parent={a['id']:a['id'] for a in assets}
    def find(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    for a in assets:
        value=int(a['phash'],16)
        for other in tree.query(value):parent[find(a['id'])]=find(other)
        tree.insert(value,a['id'])
    groups={}
    for a in assets:groups.setdefault(find(a['id']),[]).append(a)
    return [{'kind':'exact' if len({a['sha256'] for a in group})==1 else 'similar','assets':group} for group in groups.values() if len(group)>1]

def build_watch():
    global WATCHER
    # A filtered polling watcher avoids native FSEvents lifetime/fork hazards and
    # never traverses hidden caches or follows directory symlinks.
    from watchdog.observers.polling import PollingObserverVFS
    from watchdog.events import FileSystemEventHandler
    class Handler(FileSystemEventHandler):
        def __init__(self,root):self.root=root;self.timer=None;self.context=contextvars.copy_context()
        def on_any_event(self,event):
            if event.event_type in ['opened','closed_no_write'] or any(part.startswith('.') for part in Path(event.src_path).parts):return
            if event.is_directory and event.event_type=='modified':return
            if not event.is_directory and Path(event.src_path).suffix[1:].lower() not in extensions:return
            if self.timer:self.timer.cancel()
            def schedule():
                active=store.one("SELECT id FROM jobs WHERE kind='scan' AND state IN ('queued','running') AND payload LIKE ?",('%'+self.root['id']+'%',))
                if not active:jobs.create('scan',{'root_id':self.root['id']})
            self.timer=threading.Timer(3,lambda:self.context.copy().run(schedule));self.timer.daemon=True;self.timer.start()
    extensions=imaging.accepted()|media.VIDEO
    def listdir(path):
        with os.scandir(path) as entries:
            for e in entries:
                if e.name.startswith('.') or e.is_symlink() or Path(e.path).resolve()==store.PROJECT:continue
                if e.is_dir(follow_symlinks=False) or Path(e.name).suffix[1:].lower() in extensions:yield e
    WATCHER=PollingObserverVFS(stat=os.stat,listdir=listdir,polling_interval=10)
    from . import workspaces
    for entry in workspaces.registry():
        with workspaces.using(workspaces.resolve(entry['id'])):
            for root in store.rows("SELECT * FROM roots WHERE kind='library'"):
                try:WATCHER.schedule(Handler(root),root['path'],recursive=True)
                except OSError:pass
    if not WATCH_STOP.is_set():WATCHER.start()

def stop_watch():
    WATCH_STOP.set();WATCH_REQUEST.set()
    if WATCHER:
        WATCHER.stop()
        if WATCHER.is_alive():WATCHER.join(timeout=3)
    if WATCH_THREAD and WATCH_THREAD.is_alive():WATCH_THREAD.join(timeout=3)

def watch_loop():
    while not WATCH_STOP.is_set():
        WATCH_REQUEST.wait()
        WATCH_REQUEST.clear()
        if WATCH_STOP.is_set():break
        if WATCHER:
            WATCHER.stop()
            if WATCHER.is_alive():WATCHER.join(timeout=3)
        try:build_watch()
        except OSError:pass

def start_watch():
    global WATCH_THREAD
    WATCH_STOP.clear();WATCH_REQUEST.set()
    if not WATCH_THREAD or not WATCH_THREAD.is_alive():
        WATCH_THREAD=threading.Thread(target=contextvars.copy_context().run,args=(watch_loop,),name='folder-watcher',daemon=True)
        WATCH_THREAD.start()

def refresh_watch():
    # The initial recursive snapshot can be large; keep it off the API/startup path.
    start_watch()
