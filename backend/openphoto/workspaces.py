"""Immutable library contexts. Background jobs capture paths rather than a mutable active library."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from dataclasses import dataclass
import json,os,secrets,threading,time

@dataclass(frozen=True)
class LibraryContext:
    id:str
    directory:Path
    name:str
CURRENT=ContextVar('liquidframe_library',default=None)
PRIVATE=ContextVar('liquidframe_private',default=False)
LEASE=ContextVar('liquidframe_lease',default=None)
GUARD=threading.RLock()
SESSIONS={}

def registry():
    from . import store
    f=store.STATE/'.liquidframe-libraries.json'
    if not f.exists():return [{'id':'default','name':'My Library','directory':str(store.DATA)}]
    return json.loads(f.read_text())

def resolve(i='default'):
    from . import store
    if i=='default':return LibraryContext('default',store.DATA,'My Library')
    found=next((r for r in registry() if r['id']==i),None)
    if not found:raise ValueError('Library not found.')
    return LibraryContext(found['id'],Path(found['directory']),found['name'])

@contextmanager
def using(ctx,private=False):
    a=CURRENT.set(ctx);b=PRIVATE.set(private)
    try:yield ctx
    finally:CURRENT.reset(a);PRIVATE.reset(b)

def add(name,path):
    from . import store
    root=Path(path).expanduser().resolve(strict=True)
    if not root.is_dir():raise ValueError('Select an existing library folder.')
    target=root/'.liquidframe-data'
    with GUARD:
        entries=registry()
        if any(Path(e['directory'])==target for e in entries):raise ValueError('This library is already registered.')
        entry={'id':secrets.token_hex(16),'name':name[:150] or root.name,'directory':str(target)}
        target.mkdir(exist_ok=True)
        with using(LibraryContext(entry['id'],target,entry['name'])):store.init()
        entries.append(entry);f=store.STATE/'.liquidframe-libraries.json';temp=f.with_suffix('.tmp');temp.write_text(json.dumps(entries));os.replace(temp,f)
    from . import library
    library.refresh_watch()
    return entry

def private_unlocked(token,library):
    with GUARD:
        entry=SESSIONS.get(token or '')
        return bool(entry and entry['library']==library and entry['until']>time.time())

def unlock(passcode):
    from . import store
    from argon2 import PasswordHasher
    from argon2.exceptions import VerificationError
    stored=store.setting('private_passcode')
    if not stored:raise ValueError('Set a private-view passcode first.')
    last=store.setting('unlock_failures',{'count':0,'until':0})
    if last['until']>time.time():raise ValueError('Wait a moment before trying your passcode again.')
    try:PasswordHasher().verify(stored,passcode)
    except VerificationError:
        count=last['count']+1;store.set_setting('unlock_failures',{'count':count,'until':time.time()+min(60,2**min(count,6))});raise PermissionError('Incorrect passcode.')
    store.set_setting('unlock_failures',{'count':0,'until':0})
    token=secrets.token_urlsafe(32);ctx=CURRENT.get();SESSIONS[token]={'library':ctx.id if ctx else 'default','until':time.time()+600}
    return token

def setup_passcode(passcode,old=None):
    from . import store
    from argon2 import PasswordHasher
    if len(passcode)<6 or len(passcode)>128:raise ValueError('Use a passcode between 6 and 128 characters.')
    if store.setting('private_passcode'):unlock(old or '')
    store.set_setting('private_passcode',PasswordHasher().hash(passcode))
    library=CURRENT.get().id if CURRENT.get() else 'default'
    with GUARD:
        for token in list(SESSIONS):
            if SESSIONS[token]['library']==library:SESSIONS.pop(token,None)
