"""Additive catalog migrations preserve original metadata, recipes and source identities."""
import json,sqlite3,time

def apply():
    from . import store
    with store.db() as c:
        version=c.execute('PRAGMA user_version').fetchone()[0]
        if version>=3:return
        existing=c.execute('SELECT COUNT(*) FROM assets').fetchone()[0]
    if existing:
        out=store.data()/'backups'/f'catalog-schema-{version}-{int(time.time())}.sqlite3'
        with store.db() as src,sqlite3.connect(out) as dest:src.backup(dest)
    with store.db() as c:
        def columns(table,items):
            found={r[1] for r in c.execute('PRAGMA table_info('+table+')')}
            for name,definition in items.items():
                if name not in found:c.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
        columns('assets',{'title':"TEXT DEFAULT ''",'caption':"TEXT DEFAULT ''",'keywords':"TEXT DEFAULT '[]'",'rating':'INTEGER DEFAULT 0','pick_state':"TEXT DEFAULT ''",'color_label':"TEXT DEFAULT ''",'hidden':'INTEGER DEFAULT 0','deleted_at':'REAL','purged':'INTEGER DEFAULT 0','imported_at':'REAL','edited_at':'REAL','viewed_at':'REAL','exported_at':'REAL','user_meta':"TEXT DEFAULT '{}'",'media_kind':"TEXT DEFAULT 'photo'",'duration':'REAL DEFAULT 0','latitude':'REAL','longitude':'REAL','place':"TEXT DEFAULT ''",'stack_id':'TEXT','import_id':'TEXT','quality':'REAL DEFAULT 0','ocr_text':"TEXT DEFAULT ''",'camera':"TEXT DEFAULT ''",'lens':"TEXT DEFAULT ''",'iso':'REAL','aperture':'REAL','focal_length':'REAL','shutter':'REAL','flash':'INTEGER'})
        columns('albums',{'folder_id':'TEXT','kind':"TEXT DEFAULT 'album'",'rules':"TEXT DEFAULT '{}'",'cover_id':'TEXT','sort':"TEXT DEFAULT 'newest'",'position':'REAL DEFAULT 0'})
        columns('album_assets',{'position':'REAL DEFAULT 0'})
        columns('people',{'favorite':'INTEGER DEFAULT 0','hidden':'INTEGER DEFAULT 0','feature_less':'INTEGER DEFAULT 0','cover_id':'TEXT','kind':"TEXT DEFAULT 'person'",'position':'REAL DEFAULT 0','group_id':'TEXT'})
        columns('faces',{'confirmed':'INTEGER DEFAULT 0','rejected':'INTEGER DEFAULT 0'})
        columns('jobs',{'private':'INTEGER DEFAULT 0'})
        c.executescript('''
        CREATE INDEX IF NOT EXISTS asset_visibility ON assets(purged,deleted_at,hidden,captured,id);
        CREATE INDEX IF NOT EXISTS asset_rating ON assets(rating);
        CREATE INDEX IF NOT EXISTS asset_kind ON assets(media_kind);
        CREATE INDEX IF NOT EXISTS asset_stack ON assets(stack_id);
        CREATE TABLE IF NOT EXISTS album_folders(id TEXT PRIMARY KEY,name TEXT,parent_id TEXT,position REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS action_history(id TEXT PRIMARY KEY,label TEXT,before_state TEXT,after_state TEXT,undone INTEGER DEFAULT 0,created REAL);
        CREATE TABLE IF NOT EXISTS stacks(id TEXT PRIMARY KEY,kind TEXT,primary_id TEXT,name TEXT DEFAULT '',confirmed INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS imports(id TEXT PRIMARY KEY,root_id TEXT,created REAL,label TEXT);
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,kind TEXT,name TEXT,document TEXT,created REAL,updated REAL);
        CREATE TABLE IF NOT EXISTS selections(id TEXT PRIMARY KEY,created REAL,query TEXT);
        CREATE TABLE IF NOT EXISTS selection_items(selection_id TEXT,asset_id TEXT,revision INTEGER,PRIMARY KEY(selection_id,asset_id));
        CREATE TABLE IF NOT EXISTS ocr_regions(asset_id TEXT,revision INTEGER,regions TEXT,codes TEXT);
        CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY,asset_id TEXT,revision INTEGER,kind TEXT,label TEXT,box TEXT,vector BLOB,timestamp REAL DEFAULT 0,person_id TEXT);
        CREATE TABLE IF NOT EXISTS frame_search(asset_id TEXT,revision INTEGER,timestamp REAL,vector BLOB,text TEXT,PRIMARY KEY(asset_id,timestamp));
        CREATE TABLE IF NOT EXISTS collections(id TEXT PRIMARY KEY,kind TEXT,name TEXT,assets TEXT,hidden INTEGER DEFAULT 0,featured INTEGER DEFAULT 0,created REAL);
        CREATE TABLE IF NOT EXISTS people_rejections(face_id TEXT,person_id TEXT,PRIMARY KEY(face_id,person_id));
        CREATE TABLE IF NOT EXISTS sidecars(asset_id TEXT,path TEXT,kind TEXT,revision INTEGER,PRIMARY KEY(asset_id,path));
        CREATE VIRTUAL TABLE IF NOT EXISTS asset_text USING fts5(asset_id UNINDEXED,name,title,caption,keywords,ocr_text,place,tokenize='unicode61');
        CREATE TRIGGER IF NOT EXISTS asset_text_insert AFTER INSERT ON assets BEGIN
          INSERT INTO asset_text VALUES(new.id,new.name,new.title,new.caption,new.keywords,new.ocr_text,new.place); END;
        CREATE TRIGGER IF NOT EXISTS asset_text_delete AFTER DELETE ON assets BEGIN DELETE FROM asset_text WHERE asset_id=old.id; END;
        CREATE TRIGGER IF NOT EXISTS asset_text_update AFTER UPDATE OF name,title,caption,keywords,ocr_text,place ON assets BEGIN
          DELETE FROM asset_text WHERE asset_id=old.id;
          INSERT INTO asset_text VALUES(new.id,new.name,new.title,new.caption,new.keywords,new.ocr_text,new.place); END;
        ''')
        if not c.execute('SELECT 1 FROM asset_text LIMIT 1').fetchone():c.execute('INSERT INTO asset_text SELECT id,name,title,caption,keywords,ocr_text,place FROM assets')
        c.execute('UPDATE assets SET imported_at=COALESCE(imported_at,?)',(time.time(),))
        c.execute('PRAGMA user_version=3')
