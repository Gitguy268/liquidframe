from __future__ import annotations
import hashlib, json, os, sqlite3, threading, time, uuid
from pathlib import Path
from contextlib import contextmanager

PROJECT = Path(__file__).resolve().parents[2]
DATA = Path(os.getenv('LIQUIDFRAME_DATA',os.getenv('OPENPHOTO_DATA',str(PROJECT / ('.openphoto-data' if (PROJECT/'.openphoto-data').exists() else '.liquidframe-data'))))).resolve()
# Preserve an explicitly configured legacy default after the project-directory rename.
if DATA==PROJECT.parent/'openphoto'/'.openphoto-data' and not DATA.exists() and (PROJECT/'.openphoto-data').exists():
    DATA=PROJECT/'.openphoto-data'

def data():
    from .workspaces import CURRENT
    ctx=CURRENT.get()
    return ctx.directory if ctx else DATA
LOCK = threading.RLock()
CACHE_TRIM_LOCK=threading.Lock()
LAST_CACHE_TRIM=0.

def uid(): return uuid.uuid4().hex

def now(): return time.time()

def digest(path: Path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()

@contextmanager
def db():
    data().mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(data() / 'catalog.sqlite3', timeout=30)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback(); raise
    finally: con.close()

def init():
    for folder in ('previews', 'results', 'models', 'backups', 'temporary'):
        (data() / folder).mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS roots(id TEXT PRIMARY KEY,path TEXT UNIQUE NOT NULL,name TEXT,kind TEXT DEFAULT 'library',created REAL);
        CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,root_id TEXT REFERENCES roots(id),relative_path TEXT,canonical_path TEXT UNIQUE,name TEXT,extension TEXT,size INTEGER,mtime_ns INTEGER,revision INTEGER DEFAULT 1,width INTEGER DEFAULT 0,height INTEGER DEFAULT 0,bits INTEGER DEFAULT 8,captured TEXT,metadata TEXT DEFAULT '{}',status TEXT DEFAULT 'ready',error TEXT,favorite INTEGER DEFAULT 0,sha256 TEXT,phash TEXT);
        CREATE INDEX IF NOT EXISTS asset_date ON assets(captured DESC,id);
        CREATE INDEX IF NOT EXISTS asset_root ON assets(root_id,relative_path);
        CREATE INDEX IF NOT EXISTS asset_hash ON assets(sha256);
        CREATE TABLE IF NOT EXISTS albums(id TEXT PRIMARY KEY,name TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS album_assets(album_id TEXT REFERENCES albums(id) ON DELETE CASCADE,asset_id TEXT REFERENCES assets(id) ON DELETE CASCADE,PRIMARY KEY(album_id,asset_id));
        CREATE TABLE IF NOT EXISTS recipes(asset_id TEXT PRIMARY KEY REFERENCES assets(id),version INTEGER DEFAULT 1,recipe TEXT DEFAULT '{}',updated REAL);
        CREATE TABLE IF NOT EXISTS recipe_history(id TEXT PRIMARY KEY,asset_id TEXT,recipe TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS presets(id TEXT PRIMARY KEY,name TEXT,recipe TEXT);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,kind TEXT,payload TEXT,state TEXT,progress REAL DEFAULT 0,message TEXT,error TEXT,result TEXT DEFAULT '{}',created REAL,updated REAL);
        CREATE TABLE IF NOT EXISTS backups(id TEXT PRIMARY KEY,asset_id TEXT,path TEXT,original_sha TEXT,output_sha TEXT,created REAL,restored INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS embeddings(asset_id TEXT PRIMARY KEY,revision INTEGER,vector BLOB);
        CREATE TABLE IF NOT EXISTS people(id TEXT PRIMARY KEY,name TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS faces(id TEXT PRIMARY KEY,asset_id TEXT,revision INTEGER,person_id TEXT REFERENCES people(id),box TEXT,vector BLOB);
        CREATE INDEX IF NOT EXISTS faces_person ON faces(person_id);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS export_items(job_id TEXT,asset_id TEXT,path TEXT,backup_id TEXT,error TEXT,PRIMARY KEY(job_id,asset_id));

        ''')

    from . import migrations
    migrations.apply()

def rows(query, args=()):
    with db() as c: return [dict(x) for x in c.execute(query, args).fetchall()]

def one(query, args=()):
    out = rows(query, args)
    return out[0] if out else None

def execute(query, args=()):
    with LOCK, db() as c: c.execute(query, args)

def setting(key, default=None):
    r = one('SELECT value FROM settings WHERE key=?', (key,))
    return json.loads(r['value']) if r else default

def set_setting(key, value): execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key, json.dumps(value)))

def root_path(root_id):
    r = one('SELECT * FROM roots WHERE id=?', (root_id,))
    if not r or r['kind']=='detached': raise ValueError('Folder is not connected. Reconnect it before accessing its files.')
    p = Path(r['path']).resolve(strict=True)
    if not p.is_dir(): raise ValueError('Folder is unavailable.')
    return p

def confined(root: Path, relative: str, must_exist=True):
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('Path must stay inside the selected folder.')
    p = (root / relative).resolve(strict=must_exist)
    if not p.is_relative_to(root.resolve()): raise ValueError('Path escapes the selected folder.')
    return p

def asset_path(asset, expected_revision=None, check_stat=True):
    from .workspaces import PRIVATE
    current=one('SELECT hidden,deleted_at,purged FROM assets WHERE id=?',(asset['id'],))
    if not current:raise ValueError('Photo is no longer in this library.')
    if (current['hidden'] or current['deleted_at'] or current['purged']) and not PRIVATE.get():raise PermissionError('Unlock private views to access this source.')
    if expected_revision is not None and asset['revision'] != expected_revision:
        raise ValueError('Photo changed. Reopen it before continuing.')
    p = confined(root_path(asset['root_id']), asset['relative_path'])
    if str(p) != asset['canonical_path']: raise ValueError('Photo path has changed. Rescan the folder.')
    if check_stat:
        st = p.stat()
        if st.st_size != asset['size'] or st.st_mtime_ns != asset['mtime_ns']:
            raise ValueError('Photo changed outside openphoto. Rescan the folder before editing.')
    return p

def get_asset(asset_id):
    a = one('SELECT * FROM assets WHERE id=?', (asset_id,))
    if not a: raise ValueError('Photo not found.')
    from .workspaces import PRIVATE
    if (a.get('hidden') or a.get('deleted_at') or a.get('purged')) and not PRIVATE.get():raise PermissionError('Unlock private views to access this item.')
    a['metadata'] = json.loads(a['metadata'])
    a['keywords']=json.loads(a.get('keywords') or '[]')
    a['user_meta']=json.loads(a.get('user_meta') or '{}')
    return a

def get_recipe(asset_id):
    r = one('SELECT * FROM recipes WHERE asset_id=?', (asset_id,))
    return {'version': r['version'], 'recipe': json.loads(r['recipe'])} if r else {'version': 0, 'recipe': {}}

def save_recipe(asset_id, recipe, expected_version):
    get_asset(asset_id)
    from .schemas import Recipe
    recipe=Recipe.model_validate(recipe).model_dump(exclude_unset=True,exclude_none=True)
    if (recipe.get('engine') or {}).get('kind')=='darktable':
        from .native import engine_fingerprint
        recipe={**recipe,'engine':{**recipe['engine'],'fingerprint':engine_fingerprint()}}
    validate_operations(asset_id,recipe)
    with LOCK, db() as c:
        old = c.execute('SELECT * FROM recipes WHERE asset_id=?', (asset_id,)).fetchone()
        version = old['version'] if old else 0
        if expected_version != version: raise ValueError('Edits changed in another window. Reopen the photo.')
        if old:
            c.execute('INSERT INTO recipe_history VALUES(?,?,?,?)', (uid(), asset_id, old['recipe'], now()))
        c.execute('INSERT OR REPLACE INTO recipes VALUES(?,?,?,?)', (asset_id, version + 1, json.dumps(recipe), now()))
    execute('UPDATE assets SET edited_at=? WHERE id=?',(now(),asset_id))
    return {'version': version + 1, 'recipe': recipe}

def update_source(asset_id):
    a = get_asset(asset_id); p = asset_path(a, check_stat=False); s = p.stat()
    from . import imaging
    width,height,bits,metadata,captured=imaging.metadata(p)
    execute("UPDATE assets SET size=?,mtime_ns=?,width=?,height=?,bits=?,metadata=?,captured=?,revision=revision+1,sha256=NULL,phash=NULL,status='ready',error=NULL WHERE id=?", (s.st_size,s.st_mtime_ns,width,height,bits,json.dumps(metadata),captured or a['captured'],asset_id))
    execute('DELETE FROM embeddings WHERE asset_id=?', (asset_id,))
    execute('DELETE FROM faces WHERE asset_id=?', (asset_id,))
    return get_asset(asset_id)

def trim_cache(force=False):
    global LAST_CACHE_TRIM
    with CACHE_TRIM_LOCK:
        if not force and time.monotonic()-LAST_CACHE_TRIM<60:return
        LAST_CACHE_TRIM=time.monotonic()
        cap=int(setting('cache_gb',10))*1024**3
        files=[];size=0
        for p in (data()/'previews').iterdir():
            if p.suffix not in ['.webp','.png','.mp4'] or '.working.' in p.name:continue
            try:stat=p.stat()
            except FileNotFoundError:continue
            files.append((stat.st_mtime,stat.st_size,p));size+=stat.st_size
        for _,length,p in sorted(files):
            if size<=cap:break
            try:p.unlink();size-=length
            except FileNotFoundError:pass


def validate_operations(asset_id,recipe):
    allowed=set()
    for row in rows('SELECT recipe FROM recipes WHERE asset_id=? UNION ALL SELECT recipe FROM recipe_history WHERE asset_id=?',(asset_id,asset_id)):
        allowed.update(op.get('result') for op in json.loads(row['recipe']).get('operations',[]))
    for op in recipe.get('operations',[]):
        if op.get('result') not in allowed and setting('result-owner-'+str(op.get('result')))!=asset_id:raise PermissionError('An edit result must belong to this source item.')
