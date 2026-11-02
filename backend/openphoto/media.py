"""Local media tools, streaming video rendering, proxies, and reversible Live Photo effects."""
from pathlib import Path
from functools import lru_cache
import hashlib,json,os,shutil,subprocess,time
import numpy as np
from . import store,jobs
VIDEO=set('mp4 mov m4v mkv webm avi mts m2ts 3gp mpg mpeg mxf'.split())

def executable(name):
    # A matched Homebrew pair takes precedence over single-executable Python wrappers.
    for p in [Path('/opt/homebrew/bin')/name,Path('/usr/local/bin')/name]:
        if p.is_file():return str(p)
    return shutil.which(name)

def run(tool,args,timeout=120):
    binary=executable(tool)
    if not binary:raise ValueError(f'Install {tool} and restart LiquidFrame to use this feature.')
    p=subprocess.run([binary,*map(str,args)],capture_output=True,timeout=timeout,close_fds=(os.name=='nt'))
    if p.returncode:raise ValueError(p.stderr.decode(errors='replace')[-2000:] or tool+' could not process this file.')
    return p.stdout

@lru_cache(maxsize=1)
def capabilities():
    data={}
    for name in ['ffmpeg','ffprobe','tesseract','exiftool','darktable-cli','gphoto2','mtp-detect']:
        binary=executable(name)
        data[name]={'installed':bool(binary),'path':binary}
        if binary:
            try:data[name]['version']=run(name,['-version'] if name in ['ffmpeg','ffprobe'] else ['--version'],10).decode(errors='replace').splitlines()[0][:200]
            except Exception:data[name]['version']='available'
    if data['ffmpeg']['installed']:
        try:
            enc=run('ffmpeg',['-hide_banner','-encoders']).decode();data['video_export']={'mp4':'libx264' in enc,'webm':'libvpx-vp9' in enc,'hdr':False}
        except Exception:pass
    return data

def probe(path):
    return json.loads(run('ffprobe',['-v','error','-protocol_whitelist','file,pipe','-show_format','-show_streams','-of','json',str(path)],30))

def metadata(path):
    p=probe(path);s=next((s for s in p.get('streams',[]) if s.get('codec_type')=='video'),None)
    if not s:raise ValueError('No video stream was found.')
    rotation=next((x.get('rotation',0) for x in s.get('side_data_list',[]) if 'rotation' in x),0)
    w,h=s['width'],s['height']
    if abs(int(rotation))%180:w,h=h,w
    meta={'duration':float(p.get('format',{}).get('duration',0)),'codec':s.get('codec_name'),'fps':s.get('avg_frame_rate','30/1'),'rotation':rotation,'audio':any(x.get('codec_type')=='audio' for x in p['streams']),'color_primaries':s.get('color_primaries'),'color_transfer':s.get('color_transfer'),'hdr':s.get('color_transfer') in ['smpte2084','arib-std-b67'],'tags':p.get('format',{}).get('tags',{})}
    return w,h,10 if '10' in s.get('pix_fmt','') else 8,meta,meta['tags'].get('creation_time')

def frame(path,seconds=0,size=1600):
    key=hashlib.sha256(f'{path}:{path.stat().st_mtime_ns}:{seconds}:{size}'.encode()).hexdigest()
    out=store.data()/'previews'/(key+'.png')
    if not out.exists():
        content=run('ffmpeg',['-v','error','-nostdin','-protocol_whitelist','file,pipe','-ss',max(0,float(seconds)),'-i',path,'-frames:v','1','-vf',f'scale={min(4000,int(size))}:{min(4000,int(size))}:force_original_aspect_ratio=decrease','-f','image2pipe','-vcodec','png','pipe:1'])
        temp=out.with_suffix('.tmp');temp.write_bytes(content);os.replace(temp,out)
    return out

def proxy(asset_id):
    a=store.get_asset(asset_id);path=store.asset_path(a)
    key=hashlib.sha256(f'{a["id"]}:{a["revision"]}:proxy-v1'.encode()).hexdigest();out=store.data()/'previews'/(key+'.mp4')
    if out.exists():return {'ready':True,'path':out}
    active=store.one("SELECT id FROM jobs WHERE kind='proxy' AND state IN ('queued','running') AND payload LIKE ?",('%'+asset_id+'%',))
    return {'ready':False,'job_id':active['id'] if active else jobs.create('proxy',{'asset_id':asset_id,'revision':a['revision']})}

@jobs.register('proxy')
def make_proxy(payload,ctx):
    a=store.get_asset(payload['asset_id']);path=store.asset_path(a,payload['revision']);ctx.progress(.05,'Preparing local video proxy')
    key=hashlib.sha256(f'{a["id"]}:{a["revision"]}:proxy-v1'.encode()).hexdigest();out=store.data()/'previews'/(key+'.mp4');tmp=out.with_suffix('.working.mp4')
    try:
        process(['-i',str(path),'-vf','scale=1280:1280:force_original_aspect_ratio=decrease:force_divisible_by=2','-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(tmp)],ctx,max(.1,a['duration']))
        store.asset_path(a,payload['revision']);probe(tmp);os.replace(tmp,out);store.trim_cache(force=True)
    finally:tmp.unlink(missing_ok=True)
    return {'asset_id':a['id']}

def process(args,ctx,duration=1):
    log=store.data()/'temporary'/(store.uid()+'.log')
    try:
        with log.open('wb') as err:
            p=subprocess.Popen([executable('ffmpeg'),'-y','-v','error','-nostdin','-protocol_whitelist','file,pipe','-progress','pipe:1',*map(str,args)],stdout=subprocess.PIPE,stderr=err,close_fds=(os.name=='nt'))
            try:
                for raw in p.stdout:
                    ctx.check();line=raw.decode(errors='replace').strip()
                    if line.startswith('out_time_us='):
                        ctx.progress(min(.95,max(0,float(line.split('=')[1])/1e6/max(duration,.01))),'Rendering media locally')
                if p.wait():raise ValueError(log.read_text(errors='replace')[-1800:])
            except BaseException:
                p.terminate()
                try:p.wait(timeout=3)
                except subprocess.TimeoutExpired:p.kill();p.wait()
                raise
    finally:log.unlink(missing_ok=True)

def tempo(speed):
    values=[]
    while speed>2:values.append('atempo=2');speed/=2
    while speed<.5:values.append('atempo=0.5');speed*=2
    return ','.join(values+[f'atempo={speed}'])

def render_video(path,recipe,options,output,ctx):
    """Frames use the same float photo processor as the preview; memory stays bounded."""
    from . import imaging
    _,_,_,meta,_=metadata(path);duration=meta['duration'];video=recipe.get('video',{})
    start=max(0,float(video.get('start',0)));end=min(duration,float(video.get('end') or duration));speed=float(video.get('speed',1))
    if end<=start or not .25<=speed<=4:raise ValueError('Choose a valid trim and a speed between 0.25× and 4×.')
    if meta['hdr']:raise ValueError('Rendering this HDR source requires verified tone mapping, which is not available yet. Export the unmodified original to preserve its color data.')
    fps_parts=meta['fps'].split('/');fps=float(fps_parts[0])/max(float(fps_parts[-1]),1);fps=min(120,max(1,fps));frame_count=max(1,round((end-start)*fps))
    size=min(3840,int(options.get('max_size') or 1920));sample=frame(path,start,size)
    rgb,alpha,_=imaging.render(sample,recipe);w,h=rgb.width,rgb.height;w-=w%2;h-=h%2
    silent=store.data()/'temporary'/(store.uid()+'.mp4');log=store.data()/'temporary'/(store.uid()+'.log')
    decode=None;encode=None
    try:
        with log.open('wb') as err:
            decode=subprocess.Popen([executable('ffmpeg'),'-v','error','-nostdin','-protocol_whitelist','file,pipe','-ss',str(start),'-i',str(path),'-t',str(end-start),'-vf',f'scale={size}:{size}:force_original_aspect_ratio=decrease,fps={fps}','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],stdout=subprocess.PIPE,stderr=err,close_fds=(os.name=='nt'))
            # The scaled decoder dimensions match frame(), including source orientation.
            source=imaging.load(sample)[0];sw,sh=source.width,source.height;chunk=sw*sh*3
            encode=subprocess.Popen([executable('ffmpeg'),'-y','-v','error','-nostdin','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{w}x{h}','-framerate',str(fps*speed),'-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf',str(options.get('crf',20)),'-pix_fmt','yuv420p','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709',str(silent)],stdin=subprocess.PIPE,stderr=err,close_fds=(os.name=='nt'))
            n=0
            while True:
                ctx.check();raw=bytearray()
                while len(raw)<chunk:
                    piece=decode.stdout.read(chunk-len(raw))
                    if not piece:break
                    raw.extend(piece)
                if not raw:break
                if len(raw)!=chunk:raise ValueError('Video ended in an incomplete frame.')
                pixels=np.frombuffer(raw,np.uint8).reshape(sh,sw,3);im=imaging.from_array(pixels)
                edited,al=imaging.manual(im,None,recipe.get('adjustments',{}));out=imaging.array(edited)[:h,:w,:3]
                encode.stdin.write(out.tobytes());n+=1
                if n%10==0:ctx.progress(min(.85,n/frame_count*.85),f'Rendering frame {n:,}/{frame_count:,}')
            encode.stdin.close()
            if decode.wait() or encode.wait():raise ValueError(log.read_text(errors='replace')[-2000:])
        ctx.check()
        args=['-i',silent,'-ss',start,'-t',end-start,'-i',path,'-map','0:v:0','-map','1:a:0?','-c:v','copy','-af',tempo(speed),'-c:a','aac','-shortest','-movflags','+faststart',output]
        process(args,ctx,(end-start)/speed)
        result=probe(output);assert any(s.get('codec_type')=='video' for s in result['streams'])
    finally:
        for p in [decode,encode]:
            if p and p.poll() is None:p.kill();p.wait()
        silent.unlink(missing_ok=True);log.unlink(missing_ok=True)

@jobs.register('video_export')
def export_video(payload,ctx):
    a=store.get_asset(payload['asset_id']);path=store.asset_path(a,payload['revision']);root=store.root_path(payload['output_root']);out=store.confined(root,Path(a['name']).stem+'-edited.mp4',False);n=1
    while out.exists():out=store.confined(root,Path(a['name']).stem+f'-edited-{n}.mp4',False);n+=1
    temp=out.with_name('.'+store.uid()+'.mp4')
    try:render_video(path,payload.get('recipe',{}),payload.get('options',{}),temp,ctx);store.asset_path(a,payload['revision']);os.replace(temp,out)
    finally:temp.unlink(missing_ok=True)
    store.execute('UPDATE assets SET exported_at=? WHERE id=?',(store.now(),a['id']))
    return {'files':[{'path':str(out)}]}

@jobs.register('live_effect')
def live_effect(payload,ctx):
    from . import imaging
    a=store.get_asset(payload['asset_id']);stack=store.one('SELECT * FROM stacks WHERE id=?',(a['stack_id'],))
    video=store.one("SELECT * FROM assets WHERE stack_id=? AND media_kind='video'",(a['stack_id'],))
    if not stack or not video:raise ValueError('This item has no paired motion component.')
    video=store.get_asset(video['id']);path=store.asset_path(video);effect=payload.get('effect','loop');out=store.data()/'results'/(store.uid()+('.tif' if effect=='long_exposure' else '.mp4'));ctx.progress(.1,'Rendering Live Photo effect')
    if effect=='long_exposure':
        total=None;n=0
        for t in np.linspace(0,min(video['duration'],5),24,endpoint=False):
            ctx.check();rgb,_,_=imaging.load(frame(path,float(t),1600));arr=np.frombuffer(rgb.cast('float').write_to_memory(),np.float32).reshape(rgb.height,rgb.width,3).copy();total=arr if total is None else total+arr;n+=1
        im=imaging.from_array(total/n,linear=True);output=imaging.clamp(im).copy(interpretation='scrgb').colourspace('rgb16');output.set_type(imaging.pyvips.GValue.blob_type,'icc-profile-data',imaging.SRGB);output.write_to_file(str(out),compression='lzw')
    else:
        vf='[0:v]split[f][b];[b]reverse[r];[f][r]concat=n=2:v=1:a=0[v]' if effect=='bounce' else None
        args=['-i',path]
        if vf:args+=['-filter_complex',vf,'-map','[v]']
        else:args=['-stream_loop','2',*args,'-map','0:v:0']
        process(args+['-an','-c:v','libx264','-pix_fmt','yuv420p',out],ctx,max(video['duration'],1))
    store.set_setting('result-owner-'+out.name,a['id'])
    return {'result':out.name,'effect':effect,'asset_id':a['id']}
