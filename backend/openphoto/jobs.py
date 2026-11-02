from __future__ import annotations
import json, threading, traceback, contextvars
from concurrent.futures import ThreadPoolExecutor
from . import store

INDEX = ThreadPoolExecutor(max_workers=2, thread_name_prefix='index')
HEAVY = ThreadPoolExecutor(max_workers=1, thread_name_prefix='photo')
HANDLERS = {}
SUBMITTED = set()
GUARD = threading.Lock()
STOP=threading.Event()
class Cancelled(Exception):pass
class Paused(Cancelled):pass

class Context:
    def __init__(self, job_id): self.id = job_id
    def check(self):
        if STOP.is_set():raise Paused()
        r = store.one('SELECT state FROM jobs WHERE id=?', (self.id,))
        if not r or r['state'] == 'cancelled': raise Cancelled()
    def progress(self, value, message):
        self.check()
        store.execute('UPDATE jobs SET progress=?,message=?,updated=? WHERE id=?', (max(0,min(1,value)), message, store.now(), self.id))

def register(kind):
    def deco(func): HANDLERS[kind] = func; return func
    return deco

def create(kind, payload):
    if kind not in HANDLERS: raise ValueError('Unknown job type.')
    payload=dict(payload)
    if kind=='project_export':
        project=store.one('SELECT document FROM projects WHERE id=?',(payload.get('project_id'),))
        if not project:raise ValueError('Project not found.')
        payload['_asset_ids']=json.loads(project['document']).get('asset_ids',[])
    i = store.uid()
    from .workspaces import PRIVATE
    store.execute('INSERT INTO jobs(id,kind,payload,state,message,created,updated) VALUES(?,?,?,?,?,?,?)', (i,kind,json.dumps(payload),'queued','Waiting',store.now(),store.now()))
    store.execute('UPDATE jobs SET private=? WHERE id=?',(int(PRIVATE.get()),i))
    submit(i)
    return i

def submit(i):
    if STOP.is_set():return
    with GUARD:
        key=(str(store.data()),i)
        if key in SUBMITTED:return
        SUBMITTED.add(key)
    r = store.one('SELECT kind FROM jobs WHERE id=?',(i,))
    (INDEX if r['kind'] == 'scan' else HEAVY).submit(contextvars.copy_context().run,run,i)

def run(i):
    try:
        ctx = Context(i); ctx.check()
        store.execute("UPDATE jobs SET state='running',error=NULL,updated=? WHERE id=?",(store.now(),i))
        r = store.one('SELECT * FROM jobs WHERE id=?',(i,))
        result = HANDLERS[r['kind']](json.loads(r['payload']),ctx)
        ctx.check()
        store.execute("UPDATE jobs SET state='complete',progress=1,message='Complete',result=?,updated=? WHERE id=?",(json.dumps(result or {}),store.now(),i))
    except Paused:
        store.execute("UPDATE jobs SET state='queued',message='Paused for restart' WHERE id=? AND state!='cancelled'",(i,))
    except Cancelled: pass
    except Exception as e:
        store.execute("UPDATE jobs SET state='failed',message='Needs attention',error=?,updated=? WHERE id=?",(str(e),store.now(),i))
        traceback.print_exc()
    finally:
        with GUARD: SUBMITTED.discard((str(store.data()),i))

def resume():
    global INDEX,HEAVY
    if STOP.is_set():
        INDEX=ThreadPoolExecutor(max_workers=2,thread_name_prefix='index');HEAVY=ThreadPoolExecutor(max_workers=1,thread_name_prefix='photo');STOP.clear()
    store.execute("UPDATE jobs SET state='queued',message='Resuming after restart' WHERE state='running'")
    for r in store.rows("SELECT id,private FROM jobs WHERE state='queued' ORDER BY created"):
        from .workspaces import CURRENT,using,resolve
        with using(CURRENT.get() or resolve(),bool(r['private'])):submit(r['id'])

def is_private(job):
    if job.get('private'):return True
    payload=json.loads(job.get('payload') or '{}')
    related=[payload['asset_id']] if payload.get('asset_id') else [a['id'] for a in payload.get('assets',[]) if isinstance(a,dict) and 'id' in a]
    selection=payload.get('selection',{})
    related.extend(selection.get('ids',[]));related.extend(payload.get('_asset_ids',[]))
    if payload.get('project_id'):
        project=store.one('SELECT document FROM projects WHERE id=?',(payload['project_id'],))
        if project:
            doc=json.loads(project['document'])
            if doc.get('_private'):return True
            related.extend(doc.get('asset_ids',[]))
    for start in range(0,len(related),400):
        part=related[start:start+400]
        if part and store.one('SELECT id FROM assets WHERE (hidden=1 OR deleted_at IS NOT NULL OR purged=1) AND id IN ('+','.join('?' for _ in part)+') LIMIT 1',part):return True
    if selection.get('selection_id') and store.one('SELECT a.id FROM assets a JOIN selection_items s ON s.asset_id=a.id WHERE s.selection_id=? AND (a.hidden=1 OR a.deleted_at IS NOT NULL OR a.purged=1) LIMIT 1',(selection['selection_id'],)):return True
    return False

def authorize(job):
    from .workspaces import PRIVATE,LEASE,private_unlocked
    lease=LEASE.get()
    if is_private(job) and not (PRIVATE.get() and (not lease or private_unlocked(*lease))):
        raise PermissionError('Unlock private views first.')

def snapshot():
    result=store.rows('SELECT * FROM jobs ORDER BY created DESC LIMIT 50')
    for r in result:
        try:authorize(r)
        except PermissionError:r['result']='{}';r['error']=None;r['message']='Private task'
        r['result']=json.loads(r['result']);r.pop('payload',None)
    return result

def stop():
    STOP.set()
    INDEX.shutdown(wait=True,cancel_futures=True)
    HEAVY.shutdown(wait=True,cancel_futures=True)
    with GUARD:SUBMITTED.clear()
