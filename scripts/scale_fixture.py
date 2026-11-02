"""Build an isolated 100k referenced-file fixture. Never runs against an existing library."""
import os,time,shutil
from pathlib import Path
from openphoto import store,library
if store.one('SELECT COUNT(*) n FROM assets')['n'] if (store.data()/'catalog.sqlite3').exists() else 0:raise SystemExit('Scale fixture requires an empty, disposable catalog.')
store.init();start=time.perf_counter();folder=store.data().parent/'liquidframe-scale-files';folder.mkdir(exist_ok=True);source=store.PROJECT.parent/'qa-library'/'A familiar face.png'
root=library.add_root(str(folder));count=int(os.environ.get('LIQUIDFRAME_FIXTURE_COUNT','100000'));rows=[]
with store.db() as c:
 for n in range(count):
  directory=folder/f'{n//1000:03d}';directory.mkdir(exist_ok=True);p=directory/f'photo-{n:06d}.png'
  if not p.exists():os.link(source,p)
  st=p.stat();c.execute('INSERT INTO assets(id,root_id,relative_path,canonical_path,name,extension,size,mtime_ns,width,height,bits,captured,status,imported_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(f'{n:032x}',root['id'],str(p.relative_to(folder)),str(p),p.name,'png',st.st_size,st.st_mtime_ns,512,512,8,f'{2000+n%27:04d}-{1+n%12:02d}-{1+n%28:02d}T12:00:00','ready',store.now()))
print({'entries':count,'seconds':round(time.perf_counter()-start,2),'root_id':root['id']})
