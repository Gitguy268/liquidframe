"""Optional local adapters. Capability flags reflect implemented, installed functions."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys
from functools import lru_cache
from . import store,media

def darktable():
    candidates=[media.executable('darktable-cli'),'/Applications/darktable.app/Contents/MacOS/darktable-cli','/Applications/darktable.app/Contents/Resources/bin/darktable-cli']
    return next((str(p) for p in candidates if p and Path(p).is_file()),None)

def swift_helper():
    p=store.PROJECT/'native'/'macos'/'LiquidFrameBridge.app'/'Contents'/'MacOS'/'LiquidFrameBridge'
    return p if sys.platform=='darwin' and p.is_file() else None

def bridge(command,payload=None):
    p=swift_helper()
    if not p:raise ValueError('Build the optional Mac adapter in Settings first.')
    proc=subprocess.run([str(p),command],input=json.dumps(payload or {}).encode(),capture_output=True,timeout=120)
    if proc.returncode:raise ValueError(proc.stderr.decode(errors='replace')[-1500:] or 'The Mac adapter could not complete this request.')
    return json.loads(proc.stdout)

def capabilities():
    helper=swift_helper();extra={}
    if helper:
        try:extra=bridge('capabilities')
        except Exception:pass
    return {'platform':sys.platform,'darktable':bool(darktable()),'mac_bridge':bool(helper),'photo_library_import':bool(extra.get('photo_library_import')),'portrait_depth':bool(extra.get('portrait_depth')),'cinematic_focus':bool(extra.get('cinematic_focus')),'devices':{'mounted_folders':True,'gphoto2':bool(media.executable('gphoto2')),'mtp':bool(media.executable('mtp-detect'))},'details':extra}

@lru_cache(maxsize=8)
def _engine_version(binary,modified):
    result=subprocess.run([binary,'--version'],capture_output=True,text=True,timeout=15)
    if result.returncode:raise ValueError('The darktable engine could not report its version.')
    return result.stdout[:500].strip()

def engine_fingerprint():
    binary=darktable()
    if not binary:raise ValueError('Install darktable to use this RAW engine.')
    return {'name':'darktable','version':_engine_version(binary,Path(binary).stat().st_mtime_ns)}

def develop(path,engine):
    from . import imaging
    binary=darktable()
    if not binary:raise ValueError('Install darktable to use the optional RAW engine.')
    version=engine_fingerprint()['version']
    xmp=engine.get('xmp','')
    if len(xmp)>5_000_000 or '<!DOCTYPE' in xmp or '<!ENTITY' in xmp:raise ValueError('Invalid development XMP.')
    key=hashlib.sha256((str(path)+str(path.stat().st_mtime_ns)+version+xmp+str(engine.get('preset',''))).encode()).hexdigest()
    out=store.data()/'results'/(key+'.tif')
    if out.exists():return out
    folder=store.data()/'temporary'/('darktable-'+store.uid());folder.mkdir()
    # Work on a verified staging copy: even unexpected native sidecar writes stay isolated.
    source=folder/path.name;shutil.copy2(path,source);original=store.digest(path)
    if store.digest(source)!=original:raise ValueError('RAW staging copy did not verify.')
    sidecar=folder/'develop.xmp'
    if xmp:sidecar.write_text(xmp)
    temp=folder/'output.tif';config=folder/'config';cache=folder/'cache';config.mkdir();cache.mkdir()
    args=[binary,str(source)]
    if xmp:args.append(str(sidecar))
    args += [str(temp),'--apply-custom-presets','false','--core','--configdir',str(config),'--cachedir',str(cache),'--library',':memory:','--conf','write_sidecar_files=never','--conf','plugins/imageio/format/tiff/bpp=16','--conf','plugins/imageio/format/tiff/shortfile=false']
    try:
        proc=subprocess.run(args,capture_output=True,timeout=300,close_fds=(os.name=='nt'))
        if proc.returncode:raise ValueError(proc.stderr.decode(errors='replace')[-1800:])
        imaging.verify_output(temp,'tif')
        check=imaging.pyvips.Image.new_from_file(str(temp))
        if check.format not in ['ushort','float']:raise ValueError('darktable did not return a verified high-precision TIFF.')
        if store.digest(path)!=original:raise ValueError('Source changed during RAW development.')
        os.replace(temp,out)
    finally:shutil.rmtree(folder,ignore_errors=True)
    return out

def devices():
    result=[]
    if media.executable('gphoto2'):
        text=media.run('gphoto2',['--auto-detect']).decode(errors='replace')
        for line in text.splitlines()[2:]:
            pieces=line.rsplit('usb:',1)
            if len(pieces)==2:result.append({'id':'gphoto2:usb:'+pieces[1].strip(),'name':pieces[0].strip(),'adapter':'gphoto2'})
    if swift_helper():
        try:result.extend(bridge('devices').get('devices',[]))
        except Exception:pass
    return result
