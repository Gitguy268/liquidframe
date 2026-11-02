from __future__ import annotations
import base64, hashlib, io, json, os, re, shutil, subprocess, tempfile
from pathlib import Path
import numpy as np
os.environ.setdefault('VIPS_CONCURRENCY','2')
import pyvips
# The catalog handles caching. Avoid stale native operation-cache entries for mutable files
# and borrowed Python buffers; keep full-resolution pipeline memory bounded.
pyvips.cache_set_max(0)
pyvips.cache_set_max_mem(64*1024*1024)
from PIL import Image, ImageCms, ImageDraw
from . import store

RAW = set('3fr arw cr2 cr3 crw dng erf fff iiq k25 kdc mef mos mrw nef nrw orf pef raf raw rw2 rwl sr2 srf srw x3f'.split())
COMMON = set('jpg jpeg png webp avif heic heif tif tiff gif bmp jxl jp2 ico psd tga hdr exr ppm pgm pbm svg'.split())
MAGICK = shutil.which('magick')
CJXL = shutil.which('cjxl')
DJXL = shutil.which('djxl')
FORMATS = None
CODER_FAMILIES = {}
SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
LIMIT = 160_000_000
PIPELINE_REVISION='float-xyz-precision-v2'

# Never run interpreters, network protocols, or arbitrary delegates through the codec fallback.
def magick_env():
    folder = store.data() / 'magick-policy'; folder.mkdir(parents=True,exist_ok=True)
    (folder/'policy.xml').write_text('''<policymap><policy domain="delegate" rights="none" pattern="*"/><policy domain="coder" rights="none" pattern="{HTTP,HTTPS,URL,FTP,EPHEMERAL,MSL,MVG,TEXT,LABEL,CAPTION,PS,PS2,PS3,EPS,PDF,XPS}"/><policy domain="path" rights="none" pattern="@*"/><policy domain="resource" name="memory" value="512MiB"/><policy domain="resource" name="map" value="1GiB"/><policy domain="resource" name="disk" value="4GiB"/><policy domain="resource" name="time" value="120"/></policymap>''')
    return {**os.environ, 'MAGICK_CONFIGURE_PATH':str(folder)}

def command(args):
    if not MAGICK: raise ValueError('This format needs ImageMagick. Install it and restart openphoto.')
    # On POSIX, close_fds=False selects posix_spawn. Fork/vfork after native
    # image and filesystem-watcher threads have started is unsafe on macOS.
    p = subprocess.run([MAGICK,*map(str,args)],close_fds=(os.name=='nt'),capture_output=True,timeout=150,env=magick_env())
    if p.returncode: raise ValueError(p.stderr.decode(errors='replace')[-1500:] or f'Native codec exited with status {p.returncode}.')
    return p.stdout

def formats():
    global FORMATS
    if FORMATS is not None: return filter_verified(FORMATS)
    out = {}
    suffixes = {'jpeg':'jpg','png':'png','webp':'webp','tiff':'tif','heif':'heic','jxl':'jxl','gif':'gif'}
    for loader,saver,ext in [('jpegload','jpegsave','jpg'),('pngload','pngsave','png'),('webpload','webpsave','webp'),('tiffload','tiffsave','tif'),('heifload','heifsave','heic'),('jp2kload','jp2ksave','jp2'),('jxlload','jxlsave','jxl'),('gifload','gifsave','gif')]:
        read = bool(pyvips.type_find('VipsOperation',loader)); write = bool(pyvips.type_find('VipsOperation',saver))
        if read or write: out[ext]={'format':ext,'label':ext.upper(),'read':read,'write':write,'engine':'libvips','description':''}
    out['gif']={'format':'gif','label':'GIF','read':True,'write':True,'engine':'Pillow','description':'Palette animation or still image'}
    out['apng']={'format':'apng','label':'APNG','read':True,'write':True,'engine':'Pillow','description':'Animated PNG'}
    if 'heic' in out:
        out['avif']={**out['heic'],'format':'avif','label':'AVIF'}
    if MAGICK:
        for line in command(['-list','format']).decode().splitlines():
            m = re.match(r'^\s*([\w]+)\*?\s+(\w+)\s+([r-][w-][+-])\s+(.+)$',line)
            if not m: continue
            f, family, flags, desc = m.groups(); f=f.lower()
            CODER_FAMILIES[f]=family.lower()
            if f in {'pdf','ps','eps','msl','mvg','http','https','url','ftp','text','label','caption','xps','vid','ashlar','cip','clip','data','epdf','ept','ept2','ept3','ftxt','histogram','htm','html','info','inline','json','mask','mono','msvg','null','pal','pdfa','shtml','svgz','uyvy','yaml','gradient','plasma','canvas','pattern','tile','xc'}: continue
            if f in RAW or not any(x in desc.lower() for x in ('image','bitmap','pixmap','graphic','phot','png','jpeg','tiff','webp','heic','heif','avif','icon','raster','rgb','pixel','photoshop','paint','targa','farbfeld','sixel','openexr','fits','portable','jpeg-xl','jpeg xl')): continue
            ext=suffixes.get(f,f)
            if ext not in out: out[ext]={'format':ext,'label':f.upper(),'read':flags[0]=='r','write':flags[1]=='w','engine':'ImageMagick','description':desc}
    if CJXL or DJXL:
        out['jxl']={'format':'jxl','label':'JXL','read':bool(DJXL),'write':bool(CJXL),'engine':'JPEG XL','description':'JPEG XL via native cjxl/djxl'}
    for ext in sorted(RAW): out[ext]={'format':ext,'label':ext.upper(),'read':True,'write':False,'engine':'LibRaw','description':'Camera RAW development; camera compatibility varies.'}
    FORMATS=sorted(out.values(),key=lambda x:(x['format'] not in ['jpg','png','webp','avif','heic','tif','jxl','gif'],x['format']))
    return filter_verified(FORMATS)

def filter_verified(values):
    verified=store.setting('verified_encoders',None)
    if verified is None:
        try:
            import sys
            installation=json.loads((store.PROJECT/'.liquidframe-formats.json').read_text())
            verified=installation.get('encoders',{}) if installation.get('platform')==sys.platform else {}
        except (OSError,ValueError):verified={}
    return [{**f,'installed_write':f['write'],'write':bool(f['write'] and verified.get(f['format'],True)),'verified':bool(verified.get(f['format']))} for f in values]

def accepted(): return COMMON | RAW | {f['format'] for f in formats() if f['read']}

def safe_svg(path):
    # SVG is rasterized only after removing all active/external resource features.
    import xml.etree.ElementTree as ET
    try: root=ET.fromstring(path.read_bytes())
    except ET.ParseError: raise ValueError('Invalid SVG.')
    for node in root.iter():
        tag=node.tag.split('}')[-1].lower()
        if tag in {'script','foreignobject','style','image','use','a','iframe','link','animate','set'}:
            raise ValueError('SVG contains active or external resources; export a self-contained raster image instead.')
        for k,v in node.attrib.items():
            if k.lower().startswith('on') or 'href' in k.lower() or 'url(' in v.lower():
                raise ValueError('SVG external resources are not allowed.')
    return ET.tostring(root)

def load(path: Path, raw_controls=None, frame=0):
    ext=path.suffix[1:].lower()
    from . import media
    if ext in media.VIDEO:return load(media.frame(path),raw_controls,frame)
    if ext in RAW:
        import rawpy
        ctrl=raw_controls or {}
        with rawpy.imread(str(path)) as raw:
            kwargs={'output_bps':16,'gamma':(1,1),'no_auto_bright':True,'use_camera_wb':ctrl.get('white_balance','camera')=='camera','use_auto_wb':ctrl.get('white_balance')=='auto','highlight_mode':int(ctrl.get('highlight_recovery',0)),'exp_shift':2**float(ctrl.get('exposure',0)),'demosaic_algorithm':getattr(rawpy.DemosaicAlgorithm,ctrl.get('demosaic','AHD'),rawpy.DemosaicAlgorithm.AHD)}
            if ctrl.get('white_balance')=='custom':
                t=float(ctrl.get('temperature',6500)); tint=float(ctrl.get('tint',0))
                kwargs['user_wb']=[6500/t,1+max(0,tint)*.005,t/6500,1+max(0,tint)*.005]
            if raw.sizes.width*raw.sizes.height>LIMIT: raise ValueError('RAW photo exceeds the 160 megapixel processing limit.')
            rgb=raw.postprocess(**kwargs)
        im=pyvips.Image.new_from_memory(rgb.tobytes(),rgb.shape[1],rgb.shape[0],3,'ushort').copy(interpretation='rgb16')
        # LibRaw produced linear sRGB; avoid a second gamma decode.
        return (im.cast('float')/65535).copy(interpretation='scrgb'),None,{}
    if ext=='jxl' and DJXL and not pyvips.type_find('VipsOperation','jxlload'):
        tmp=store.data()/'temporary'/(store.uid()+'.png')
        try:
            run=subprocess.run([DJXL,str(path),str(tmp)],close_fds=(os.name=='nt'),capture_output=True,timeout=120)
            if run.returncode: raise ValueError(run.stderr.decode(errors='replace')[-1000:])
            im=pyvips.Image.new_from_buffer(tmp.read_bytes(),'')
        finally:tmp.unlink(missing_ok=True)
    else:
        im=None
    if ext in ['gif','apng']:
        with Image.open(path) as pil:
            try:pil.seek(frame)
            except EOFError:raise ValueError('This frame does not exist.')
            if pil.width*pil.height>LIMIT:raise ValueError('Photo exceeds the processing limit.')
            pixels=np.asarray(pil.convert('RGBA')).copy()
        im=pyvips.Image.new_from_memory(pixels.tobytes(),pixels.shape[1],pixels.shape[0],4,'uchar').copy(interpretation='srgb')
    try:
        if im is None: im=pyvips.Image.new_from_buffer(safe_svg(path),'') if ext=='svg' else pyvips.Image.new_from_file(str(path),access='sequential',**({'page':frame} if frame else {}))
    except pyvips.Error:
        if ext=='svg': raise
        content=command([str(path)+f'[{frame}]','tiff:-'])
        im=pyvips.Image.new_from_buffer(content,'')
    if im.width*im.height>LIMIT: raise ValueError('Photo exceeds the 160 megapixel processing limit. Convert or resize it first.')
    im=im.autorot()
    meta={}
    for k in ['icc-profile-data','exif-data','xmp-data','iptc-data']:
        if im.get_typeof(k): meta[k]=im.get(k)
    alpha=None
    if im.hasalpha():
        alpha=im.extract_band(im.bands-1).cast('float')/(65535 if im.format=='ushort' else 1 if im.format in ['float','double'] else 255)
        im=im.extract_band(0,n=im.bands-1)
    if im.bands==1: im=im.bandjoin([im,im])
    if im.get_typeof('icc-profile-data'):
        try: im=im.icc_import(embedded=True,pcs='xyz').colourspace('scrgb')
        except pyvips.Error as e: raise ValueError('Cannot interpret embedded ICC profile: '+str(e))
    else: im=im.colourspace('scrgb')
    return im,alpha,meta

def clamp(im, low=0, high=1): return (im<low).ifthenelse(low,(im>high).ifthenelse(high,im))

def curve(im, points):
    if not points or len(points)<2: return im
    points=sorted(points)
    # A piecewise linear float LUT avoids reducing the working image to 8 bits.
    xs=np.array([p[0] for p in points]); ys=np.array([p[1] for p in points])
    lut=np.interp(np.linspace(0,1,65536),xs,ys).astype(np.float32)
    table=pyvips.Image.new_from_memory(lut.tobytes(),65536,1,1,'float')
    return (clamp(im)*65535).cast('ushort').maplut(table).copy(interpretation='scrgb')

def manual(rgb, alpha, p):
    if p.get('disabled_groups'):
        p=dict(p);advanced=dict(p.get('advanced',{}));groups={'Light':['brightness','brilliance','definition'],'White Balance':['white_balance_sample','white_balance_mode'],'Curves and Levels':['curves','levels'],'Selective Color':['selective_color'],'Black and White':['black_white'],'Sharpen':['sharpen_detail'],'Noise Reduction':['denoise_detail'],'Vignette':['vignette_detail'],'Retouch':['retouch'],'Perspective':['perspective']}
        for group in p['disabled_groups']:
            for key in groups.get(group,[]):advanced.pop(key,None)
            for key in {'Light':['exposure','contrast','highlights','shadows','whites','blacks'],'White Balance':['temperature','tint'],'Curves and Levels':['curve'],'Sharpen':['sharpen'],'Noise Reduction':['denoise'],'Vignette':['vignette']}.get(group,[]):p.pop(key,None)
        p['advanced']=advanced
    rgb=rgb*(2**float(p.get('exposure',0)))
    temperature=float(p.get('temperature',0))/100; tint=float(p.get('tint',0))/100
    rgb=rgb*[1+temperature*.22,1+tint*.12,1-temperature*.22]
    l=rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722
    sh=float(p.get('shadows',0))/100; hi=float(p.get('highlights',0))/100
    rgb=rgb+sh*.22*(1-clamp(l))**3+hi*.22*clamp(l)**3
    rgb=rgb+float(p.get('blacks',0))/100*.12*(1-clamp(l))**4+float(p.get('whites',0))/100*.12*clamp(l)**4
    rgb=(rgb-.18)*(1+float(p.get('contrast',0))/100)+.18
    l=rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722
    sat=1+float(p.get('saturation',0))/100
    spread=(rgb.maxpair(rgb.rot(90)) if False else (rgb[0]-rgb[1]).abs()+(rgb[1]-rgb[2]).abs())
    vib=float(p.get('vibrance',0))/100*(1-clamp(spread))
    rgb=l+(rgb-l)*(sat+vib)
    rgb=curve(rgb,p.get('curve'))
    hsl=p.get('hsl',{})
    if any(float(hsl.get(k,0)) for k in ('hue','saturation','lightness')):
        # HSL on nonlinear RGB floats: never pass through libvips' 8-bit HSV representation.
        c=clamp(rgb);c=(c<=.0031308).ifthenelse(c*12.92,1.055*c**(1/2.4)-.055)
        r,g,b=c[0],c[1],c[2]
        mx=(r>g).ifthenelse(r,g);mx=(mx>b).ifthenelse(mx,b)
        mn=(r<g).ifthenelse(r,g);mn=(mn<b).ifthenelse(mn,b)
        delta=mx-mn;l=(mx+mn)/2
        h=(mx==r).ifthenelse(((g-b)/(delta+1e-7))%6,(mx==g).ifthenelse((b-r)/(delta+1e-7)+2,(r-g)/(delta+1e-7)+4))*60
        h=(h+float(hsl.get('hue',0))+360)%360
        sat=clamp(delta/(1-(l*2-1).abs()+1e-7)*(1+float(hsl.get('saturation',0))/100))
        l=clamp(l+float(hsl.get('lightness',0))/100*.5)
        chroma=(1-(2*l-1).abs())*sat;x=chroma*(1-((h/60)%2-1).abs());m=l-chroma/2
        rr=(h<60).ifthenelse(chroma,(h<120).ifthenelse(x,(h<240).ifthenelse(0,(h<300).ifthenelse(x,chroma))))
        gg=(h<60).ifthenelse(x,(h<180).ifthenelse(chroma,(h<240).ifthenelse(x,0)))
        bb=(h<120).ifthenelse(0,(h<180).ifthenelse(x,(h<300).ifthenelse(chroma,x)))
        c=rr.bandjoin([gg,bb])+m
        rgb=(c<=.04045).ifthenelse(c/12.92,((c+.055)/1.055)**2.4).copy(interpretation='scrgb')
    dn=float(p.get('denoise',0))
    if dn and not p.get('advanced',{}).get('denoise_detail'): rgb=rgb*(1-dn/100*.7)+rgb.gaussblur(.3+dn/40)*(dn/100*.7)
    sharp=float(p.get('sharpen',0))
    if sharp and not p.get('advanced',{}).get('sharpen_detail'): rgb=rgb+(rgb-rgb.gaussblur(1))*sharp/100
    vig=float(p.get('vignette',0))/100
    if vig and not p.get('advanced',{}).get('vignette_detail'):
        xy=pyvips.Image.xyz(rgb.width,rgb.height)
        radius=((xy[0]/max(rgb.width-1,1)-.5)**2+(xy[1]/max(rgb.height-1,1)-.5)**2)*2
        rgb=rgb*(1-clamp(radius)*vig*.7)
    if p.get('advanced'):
        from .adjustments import apply
        rgb,alpha=apply(rgb,alpha,p['advanced'],p)
    crop=p.get('crop')
    if crop:
        x,y,w,h=crop; left=int(x*rgb.width); top=int(y*rgb.height)
        width=max(1,min(rgb.width-left,int(w*rgb.width))); height=max(1,min(rgb.height-top,int(h*rgb.height)))
        rgb=rgb.crop(left,top,width,height)
        if alpha is not None: alpha=alpha.crop(left,top,width,height)
    angle=float(p.get('straighten',0))
    if angle:
        rgb=rgb.similarity(angle=angle,background=[0,0,0])
        if alpha is not None: alpha=alpha.similarity(angle=angle,background=[0])
    turn=int(p.get('rotate',0))%360
    if turn:
        rgb=rgb.rot({90:'d90',180:'d180',270:'d270'}[turn])
        if alpha is not None: alpha=alpha.rot({90:'d90',180:'d180',270:'d270'}[turn])
    for flag,direction in [('flip_h','horizontal'),('flip_v','vertical')]:
        if p.get(flag):
            rgb=rgb.flip(direction)
            if alpha is not None: alpha=alpha.flip(direction)
    return rgb,alpha

def render(path, recipe=None, preview=None):
    recipe=recipe or {}
    engine=recipe.get('engine') or {}
    if engine.get('kind')=='darktable' and path.suffix[1:].lower() in RAW:
        from .native import develop
        rgb,alpha,meta=load(develop(path,engine))
    else:rgb,alpha,meta=load(path,recipe.get('raw'),recipe.get('frame',0))
    if preview and max(rgb.width,rgb.height)>preview:
        scale=preview/max(rgb.width,rgb.height); rgb=rgb.resize(scale)
        if alpha is not None: alpha=alpha.resize(scale)
    rgb,alpha=manual(rgb,alpha,recipe.get('adjustments',{}))
    for op in recipe.get('operations',[]):
        result=store.confined(store.data()/'results',op['result'])
        rgb,alpha,_=load(result)
        if preview and max(rgb.width,rgb.height)>preview:
            scale=preview/max(rgb.width,rgb.height); rgb=rgb.resize(scale)
            if alpha is not None: alpha=alpha.resize(scale)
        rgb,alpha=manual(rgb,alpha,op.get('adjustments',{}))
    return rgb,alpha,meta

def display(rgb,alpha=None):
    out=clamp(rgb).copy(interpretation='scrgb').colourspace('srgb')
    if alpha is not None: out=out.bandjoin(clamp(alpha)*255)
    return out

def array(rgb):
    im=display(rgb).cast('uchar'); return np.frombuffer(im.write_to_memory(),np.uint8).reshape(im.height,im.width,im.bands).copy()

def from_array(a, linear=False):
    a=np.ascontiguousarray(a)
    typ='uchar' if a.dtype==np.uint8 else 'ushort' if a.dtype==np.uint16 else 'float'
    im=pyvips.Image.new_from_memory(a.tobytes(),a.shape[1],a.shape[0],a.shape[2] if a.ndim==3 else 1,typ)
    return im.copy(interpretation='scrgb' if linear else 'rgb16' if typ=='ushort' else 'srgb').colourspace('scrgb')

def metadata(path):
    ext=path.suffix[1:].lower()
    from . import media
    if ext in media.VIDEO:return media.metadata(path)
    if ext in ['gif','apng']:
        with Image.open(path) as pil:return pil.width,pil.height,8,{'profile':'assumed sRGB','pages':getattr(pil,'n_frames',1)},None
    if ext in RAW:
        import rawpy
        with rawpy.imread(str(path)) as r:
            return r.sizes.width,r.sizes.height,16,{'camera_raw':True},None
    try: im=pyvips.Image.new_from_buffer(safe_svg(path),'') if ext=='svg' else pyvips.Image.new_from_file(str(path))
    except pyvips.Error:
        rgb,_,_=load(path); return rgb.width,rgb.height,8,{},None
    im=im.autorot()
    data={}; captured=None
    for k in im.get_fields():
        if k.startswith('exif-'):
            value=str(im.get(k)); data[k]=value
            if k in ('exif-ifd2-DateTimeOriginal','exif-ifd0-DateTime'):
                m=re.search(r'(\d{4}):(\d{2}):(\d{2}) (\d{2}:\d{2}:\d{2})',value)
                if m: captured=f'{m[1]}-{m[2]}-{m[3]}T{m[4]}'
    data['profile']='embedded' if im.get_typeof('icc-profile-data') else 'assumed sRGB'
    data['pages']=int(im.get('n-pages')) if im.get_typeof('n-pages') else 1
    return im.width,im.height,16 if im.format=='ushort' else 32 if im.format=='float' else 8,data,captured

def encode(path, recipe, options, output):
    fmt=options.get('format','jpg').lower(); fmt={'jpeg':'jpg','tiff':'tif','heif':'heic'}.get(fmt,fmt)
    cap=next((f for f in formats() if f['format']==fmt and f['write']),None)
    if not cap: raise ValueError('No verified encoder is installed for '+fmt.upper())
    if options.get('preserve_frames'):
        if recipe.get('operations') or any(recipe.get('adjustments',{}).values()) or recipe.get('raw') or recipe.get('frame',0):
            raise ValueError('Preserve animation/pages is available for conversion without edits only.')
        if path.suffix[1:].lower()=='svg': safe_svg(path)
        if fmt in ['gif','apng']:
            from PIL import ImageSequence
            with Image.open(path) as im:
                if im.width*im.height*getattr(im,'n_frames',1)>LIMIT:raise ValueError('Animation exceeds the total pixel processing limit.')
                frames=[frame.convert('RGBA').copy() for frame in ImageSequence.Iterator(im)]
                durations=[frame.info.get('duration',100) for frame in ImageSequence.Iterator(im)]
                frames[0].save(output,format='GIF' if fmt=='gif' else 'PNG',save_all=True,append_images=frames[1:],duration=durations,loop=im.info.get('loop',0))
            verify_output(output,fmt);return
        args=[path]
        if options.get('strip_metadata'): args+=['-strip']
        if options.get('max_size'): args+=['-resize',f'{options["max_size"]}x{options["max_size"]}>']
        args+=['-quality',str(options.get('quality',90)),f'{fmt}:{output}']
        command(args); verify_output(output,fmt); return
    rgb,alpha,meta=render(path,recipe)
    size=options.get('max_size')
    if size and max(rgb.width,rgb.height)>size:
        s=size/max(rgb.width,rgb.height); rgb=rgb.resize(s)
        if alpha is not None: alpha=alpha.resize(s)
    if options.get('width') or options.get('height'):
        width=int(options.get('width') or rgb.width*int(options['height'])/rgb.height)
        height=int(options.get('height') or rgb.height*width/rgb.width)
        if width*height>LIMIT: raise ValueError('Requested output exceeds 160 megapixels.')
        sx=width/rgb.width; sy=height/rgb.height; rgb=rgb.resize(sx,vscale=sy)
        if alpha is not None: alpha=alpha.resize(sx,vscale=sy)
    bits=int(options.get('bits',8)); supports_alpha=fmt in ['png','webp','tif','avif','heic','jxl','gif','psd','exr']
    if alpha is not None and not supports_alpha:
        color=options.get('background','#ffffff').lstrip('#'); bg=np.array([int(color[i:i+2],16)/255 for i in (0,2,4)])
        bg=np.where(bg<=.04045,bg/12.92,((bg+.055)/1.055)**2.4)
        rgb=rgb*alpha+(1-alpha)*bg.tolist(); alpha=None
    out=clamp(rgb).copy(interpretation='scrgb').colourspace('rgb16' if bits==16 and fmt in ['png','tif'] else 'srgb')
    profile=options.get('profile','srgb')
    if profile=='source' and meta.get('icc-profile-data'):
        pf=store.data()/'temporary'/f'{hashlib.sha256(meta["icc-profile-data"]).hexdigest()}.icc'
        pf.write_bytes(meta['icc-profile-data'])
        # Export directly from the unbounded D65 working pixels. Clipping through
        # an intermediate sRGB image would discard source-profile gamut.
        out=rgb.copy(interpretation='scrgb').colourspace('xyz').icc_export(output_profile=str(pf),pcs='xyz',depth=16 if bits==16 else 8,intent='relative')
    else:
        out=out.copy(); out.set_type(pyvips.GValue.blob_type,'icc-profile-data',SRGB)
    if alpha is not None: out=out.bandjoin(clamp(alpha)*(65535 if out.format=='ushort' else 255))
    out=out.cast('ushort' if bits==16 and fmt in ['png','tif'] else 'uchar')
    if not options.get('strip_metadata',False):
        for k,v in meta.items():
            if k!='icc-profile-data':
                if k=='exif-data':
                    exif=Image.Exif();exif.load(v);exif[274]=1;v=exif.tobytes()
                out.set_type(pyvips.GValue.blob_type,k,v)
    else:
        for k in ('exif-data','xmp-data','iptc-data'):
            if out.get_typeof(k): out.remove(k)
    out.set_type(pyvips.GValue.gint_type,'orientation',1)
    if out.get_typeof('exif-ifd0-Orientation'):out.remove('exif-ifd0-Orientation')
    kwargs={}; quality=int(options.get('quality',90))
    if fmt in ['jpg','webp','avif','heic','jxl']: kwargs['Q']=quality
    if fmt=='avif': kwargs['compression']='av1'
    if fmt=='tif': kwargs['compression']='lzw'
    try:
        if fmt in ['gif','apng']:
            pil=Image.open(io.BytesIO(out.write_to_buffer('.png')))
            pil.save(output,format='GIF' if fmt=='gif' else 'PNG',save_all=True,duration=100,loop=0)
        elif cap['engine']=='libvips':
            suffix={'tif':'.tif','jpg':'.jpg','avif':'.avif','heic':'.heic'}.get(fmt,'.'+fmt)
            try: output.write_bytes(out.write_to_buffer(suffix,**kwargs))
            except pyvips.Error:
                if not MAGICK: raise
                tmp=store.data()/'temporary'/f'{store.uid()}.tif';tmp.write_bytes(out.write_to_buffer('.tif'))
                try:command([tmp,'-quality',str(quality),f'{fmt}:{output}'])
                finally:tmp.unlink(missing_ok=True)
        else:
            content=out.write_to_buffer('.png' if fmt=='jxl' else '.tif')
            tmp=store.data()/'temporary'/f'{store.uid()}.png' if fmt=='jxl' else store.data()/'temporary'/f'{store.uid()}.tif'; tmp.write_bytes(content)
            try:
                if fmt=='jxl' and CJXL:
                    run=subprocess.run([CJXL,str(tmp),str(output),'-q',str(quality)],close_fds=(os.name=='nt'),capture_output=True,timeout=120)
                    if run.returncode: raise ValueError(run.stderr.decode(errors='replace')[-1000:])
                else: command([tmp,'-quality',str(quality),f'{fmt}:{output}'])
            finally: tmp.unlink(missing_ok=True)
    except Exception:
        output.unlink(missing_ok=True); raise
    verify_output(output,fmt)

def verify_native_encoding(path,fmt):
    if not CODER_FAMILIES:formats()
    detected=set(command(['identify','-format','%m\n',str(path)]).decode().strip().lower().splitlines())
    alias={'jpg':'jpeg','tif':'tiff'}
    expected=CODER_FAMILIES.get(fmt,alias.get(fmt,fmt))
    if not detected or any(CODER_FAMILIES.get(f,alias.get(f,f))!=expected for f in detected):
        raise ValueError('Encoder returned a different format than requested.')

def verify_output(path,fmt):
    if not path.exists() or not path.stat().st_size: raise ValueError('Encoder produced an empty file.')
    if fmt in ['gif','apng']:
        with Image.open(path) as pil:
            if pil.format!=('GIF' if fmt=='gif' else 'PNG'):raise ValueError('Encoder returned a different format than requested.')
            pil.load()
        return
    try:
        im=pyvips.Image.new_from_file(str(path)); im.avg()
        loader=str(im.get('vips-loader')) if im.get_typeof('vips-loader') else ''
        expected={'jpg':'jpeg','png':'png','webp':'webp','tif':'tiff','heic':'heif','avif':'heif','jxl':'jxl','gif':'gif','jp2':'jp2k'}.get(fmt)
        if expected and expected not in loader.lower(): raise ValueError('Encoder returned a different format than requested.')
        if expected is None:verify_native_encoding(path,fmt)
        if fmt=='avif' and b'avif' not in path.read_bytes()[:64]: raise ValueError('AVIF output has an incorrect file signature.')
    except pyvips.Error:
        if fmt=='jxl' and DJXL:
            raw,_,_=load(path); raw.avg();
            if path.read_bytes()[:2]!=b'\xff\x0a' and b'JXL ' not in path.read_bytes()[:16]: raise ValueError('Incorrect JXL signature.')
            return
        verify_native_encoding(path,fmt)

def preview(asset_id, size=768, recipe=None):
    a=store.get_asset(asset_id); path=store.asset_path(a)
    recipe=store.get_recipe(asset_id)['recipe'] if recipe is None else recipe
    poster=store.setting('poster-'+asset_id,0) if a.get('media_kind')=='video' else None
    key=hashlib.sha256(json.dumps([PIPELINE_REVISION,asset_id,a['revision'],size,recipe,poster],sort_keys=True).encode()).hexdigest()
    p=store.data()/'previews'/f'{key}.webp'
    if not p.exists():
        if poster is not None:
            from . import media
            path=media.frame(path,poster,size)
        rgb,alpha,_=render(path,recipe,preview=size)
        rgb=display(rgb,alpha); content=rgb.write_to_buffer('.webp',Q=85)
        temp=p.with_suffix('.'+store.uid()+'.tmp'); temp.write_bytes(content); os.replace(temp,p)
        store.trim_cache()
    else: os.utime(p,None)
    return p

def paint_mask(strokes,width,height,feather=0):
    im=Image.new('L',(width,height),0)
    d=ImageDraw.Draw(im)
    for stroke in strokes:
        radius=max(1,int(float(stroke.get('radius',.025))*min(width,height)))
        points=[(float(x)*width,float(y)*height) for x,y in stroke['points']]
        fill=0 if stroke.get('erase') else 255
        if len(points)>1: d.line(points,fill=fill,width=radius*2,joint='curve')
        for x,y in points: d.ellipse((x-radius,y-radius,x+radius,y+radius),fill=fill)
    if feather:
        from PIL import ImageFilter
        im=im.filter(ImageFilter.GaussianBlur(feather))
    return np.asarray(im,dtype=np.float32)/255
