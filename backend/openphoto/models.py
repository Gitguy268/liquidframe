from __future__ import annotations
import functools, gc, hashlib, json, os, threading
from pathlib import Path
import httpx
import numpy as np
import cv2
from PIL import Image
from . import store, imaging, jobs

MANIFEST = json.loads(Path(__file__).with_name('models.json').read_text()) if Path(__file__).with_name('models.json').exists() else {}
DOWNLOAD_LOCK = threading.Lock()

def directory(key):
    if key not in MANIFEST: raise ValueError('Unknown model.')
    return store.data()/'models'/key

def installed(key):
    d=directory(key)
    try: verified=json.loads((d/'verified.json').read_text())
    except (FileNotFoundError,json.JSONDecodeError): return False
    return all(verified.get(f['name'])==f['sha256'] and (d/f['name']).is_file() and (d/f['name']).stat().st_size==f['size'] for f in MANIFEST[key]['files'])

def status():
    return [{'id':k,'label':m['label'],'license':m['license'],'source':m['source'],'bytes':sum(f['size'] for f in m['files']),'installed':installed(k)} for k,m in MANIFEST.items()]

def ensure(key, ctx, start=0, span=.3):
    with DOWNLOAD_LOCK:
        if installed(key): return directory(key)
        m=MANIFEST[key]; d=directory(key); d.mkdir(parents=True,exist_ok=True)
        total=sum(f['size'] for f in m['files']); done=0; verified={}
        with httpx.Client(follow_redirects=True,timeout=httpx.Timeout(120,connect=30),trust_env=False) as client:
            for f in m['files']:
                ctx.check(); p=store.confined(d,f['name'],must_exist=False); p.parent.mkdir(parents=True,exist_ok=True)
                if p.exists() and p.stat().st_size==f['size'] and store.digest(p)==f['sha256']:
                    verified[f['name']]=f['sha256']; done+=f['size']; continue
                partial=p.with_suffix(p.suffix+'.partial'); offset=partial.stat().st_size if partial.exists() else 0
                headers={'Range':f'bytes={offset}-'} if offset else {}
                with client.stream('GET',f['url'],headers=headers) as r:
                    r.raise_for_status()
                    if r.status_code!=206: offset=0
                    with partial.open('ab' if offset else 'wb') as out:
                        downloaded=offset
                        for chunk in r.iter_bytes(1024*1024):
                            ctx.check(); out.write(chunk); downloaded+=len(chunk)
                            ctx.progress(start+span*(done+downloaded)/total,f'Downloading {m["label"]} · {int((done+downloaded)/total*100)}%')
                        out.flush(); os.fsync(out.fileno())
                if partial.stat().st_size!=f['size'] or store.digest(partial)!=f['sha256']:
                    partial.unlink(missing_ok=True); raise ValueError('Model checksum did not match. Retry the download.')
                os.replace(partial,p); verified[f['name']]=f['sha256']; done+=f['size']
        (d/'verified.json').write_text(json.dumps(verified))
        return d

@jobs.register('model')
def download(payload,ctx):
    keys=payload.get('models',[])
    for i,key in enumerate(keys): ensure(key,ctx,i/max(len(keys),1),1/max(len(keys),1))
    return {'models':keys}

@functools.lru_cache(maxsize=2)
def session(key,name):
    import onnxruntime as ort
    ort.disable_telemetry_events()
    if not installed(key): raise ValueError('Download the model first.')
    options=ort.SessionOptions(); options.intra_op_num_threads=min(4,os.cpu_count() or 1)
    options.inter_op_num_threads=1
    f=next(f for f in MANIFEST[key]['files'] if f['name']==name)
    if store.digest(directory(key)/name)!=f['sha256']:raise ValueError('Cached model is damaged. Remove that model pack and download it again.')
    return ort.InferenceSession(str(directory(key)/name),sess_options=options,providers=['CPUExecutionProvider'])

def infer(sess, tensor): return sess.run(None,{sess.get_inputs()[0].name:tensor})

def resize_rgb(a,side):
    b=cv2.resize(a,(side,side),interpolation=cv2.INTER_LINEAR).astype(np.float32)/255
    return np.transpose(b,(2,0,1))[None]

def cutout(a,ctx,strokes=None,feather=1):
    ensure('background',ctx)
    ctx.progress(.35,'Finding the subject locally…')
    s=session('background','onnx/model.onnx')
    side=s.get_inputs()[0].shape[-1]; side=side if isinstance(side,int) else 1024
    x=resize_rgb(a,side)
    x=(x-np.array([.485,.456,.406],np.float32)[None,:,None,None])/np.array([.229,.224,.225],np.float32)[None,:,None,None]
    result=infer(s,x)[0].squeeze(); ctx.check()
    if result.min()<0 or result.max()>1: result=1/(1+np.exp(-np.clip(result,-30,30)))
    mask=cv2.resize(result,(a.shape[1],a.shape[0]),interpolation=cv2.INTER_LINEAR)
    for stroke in strokes or []:
        patch=imaging.paint_mask([{**stroke,'erase':False}],a.shape[1],a.shape[0])
        mask=mask*(1-patch) if stroke.get('erase') else mask*(1-patch)+patch
    if feather: mask=cv2.GaussianBlur(mask,(0,0),float(feather))
    return np.clip(mask,0,1)

def cleanup(a,strokes,ctx,feather=3):
    mask=imaging.paint_mask(strokes,a.shape[1],a.shape[0])
    yy,xx=np.where(mask>0)
    if not len(xx): raise ValueError('Paint over the object you want to remove first.')
    ensure('cleanup',ctx)
    pad=max(32,int(max(xx.max()-xx.min(),yy.max()-yy.min())*.4))
    left=max(0,int(xx.min())-pad); top=max(0,int(yy.min())-pad)
    right=min(a.shape[1],int(xx.max())+pad+1); bottom=min(a.shape[0],int(yy.max())+pad+1)
    # Square letterboxing preserves proportions; crop only the padded repair region.
    roi=a[top:bottom,left:right]; rm=mask[top:bottom,left:right]
    h,w=roi.shape[:2]; side=max(h,w)
    image=np.pad(roi,((0,side-h),(0,side-w),(0,0)),mode='reflect')
    padded=np.pad(rm,((0,side-h),(0,side-w)),mode='constant')
    s=session('cleanup','lama_fp32.onnx')
    inputs={}
    for x in s.get_inputs():
        inputs[x.name]=resize_rgb(image,512) if len(x.shape)==4 and x.shape[1]==3 else cv2.resize(padded,(512,512),interpolation=cv2.INTER_NEAREST)[None,None].astype(np.float32)
    ctx.progress(.45,'Repairing the selected region…')
    out=s.run(None,inputs)[0];ctx.check()
    b=np.transpose(out.squeeze(),(1,2,0))
    if b.max()<=1.5: b=b*255
    b=cv2.resize(b,(side,side),interpolation=cv2.INTER_CUBIC)[:h,:w]
    # Feather inward: absolutely no pixel outside the painted mask is changed.
    distance=cv2.distanceTransform((rm>0).astype(np.uint8),cv2.DIST_L2,3)
    blend=np.clip(distance/max(float(feather),1),0,1)[...,None]
    result=a.copy(); result[top:bottom,left:right]=np.clip(roi*(1-blend)+b*blend,0,255).astype(np.uint8)
    return result

@functools.lru_cache(maxsize=1)
def enhancement_model(strength,device="cpu"):
    import torch
    from torch import nn
    # SRVGGNetCompact architecture adapted from xinntao/Real-ESRGAN, BSD-3-Clause.
    class SRVGG(nn.Module):
        def __init__(self):
            super().__init__()
            layers=[nn.Conv2d(3,64,3,1,1),nn.PReLU(num_parameters=64)]
            for _ in range(32): layers.extend([nn.Conv2d(64,64,3,1,1),nn.PReLU(num_parameters=64)])
            layers.append(nn.Conv2d(64,48,3,1,1)); self.body=nn.ModuleList(layers); self.upsampler=nn.PixelShuffle(4)
        def forward(self,x):
            out=x
            for layer in self.body: out=layer(out)
            return self.upsampler(out)+torch.nn.functional.interpolate(x,scale_factor=4,mode='nearest')
    d=directory('enhance'); model=SRVGG()
    strong=torch.load(d/'realesr-general-x4v3.pth',map_location='cpu',weights_only=True)['params']
    weak=torch.load(d/'realesr-general-wdn-x4v3.pth',map_location='cpu',weights_only=True)['params']
    model.load_state_dict({k:strong[k]*strength+weak[k]*(1-strength) for k in strong})
    torch.set_num_threads(min(4,os.cpu_count() or 1)); return model.eval().to(device)

def enhance(a,scale,strength,ctx):
    import torch
    ensure('enhance',ctx)
    device='cpu'
    if store.setting('acceleration','cpu')=='auto':
        if torch.cuda.is_available():device='cuda'
        elif torch.backends.mps.is_available():device='mps'
    model=enhancement_model(round(strength,2),device)
    h,w=a.shape[:2]
    if h*w*16>imaging.LIMIT: raise ValueError('4× intermediate output exceeds 160 megapixels. Resize the source before enhancement.')
    out=np.empty((h*4,w*4,3),np.uint8); tile=128; pad=16
    count=((w+tile-1)//tile)*((h+tile-1)//tile); i=0
    with torch.inference_mode():
        for y in range(0,h,tile):
            for x in range(0,w,tile):
                ctx.progress(.3+.6*i/count,f'Restoring detail · tile {i+1}/{count}')
                y1=max(0,y-pad);x1=max(0,x-pad);y2=min(h,y+tile+pad);x2=min(w,x+tile+pad)
                t=torch.from_numpy(np.ascontiguousarray(a[y1:y2,x1:x2].transpose(2,0,1))).float()[None]/255
                try:b=model(t.to(device)).clamp(0,1)[0].permute(1,2,0).cpu().numpy()*255
                except RuntimeError:
                    if device=='cpu':raise
                    device='cpu';model=enhancement_model(round(strength,2),'cpu')
                    b=model(t).clamp(0,1)[0].permute(1,2,0).numpy()*255
                yh=min(tile,h-y);xw=min(tile,w-x)
                out[y*4:(y+yh)*4,x*4:(x+xw)*4]=b[(y-y1)*4:(y-y1+yh)*4,(x-x1)*4:(x-x1+xw)*4].round().astype(np.uint8);i+=1
    if scale!=4: out=cv2.resize(out,(w*scale,h*scale),interpolation=cv2.INTER_LANCZOS4)
    return out

@jobs.register('ai')
def ai(payload,ctx):
    a=store.get_asset(payload['asset_id']); path=store.asset_path(a,payload['revision'])
    recipe=payload.get('recipe') or store.get_recipe(a['id'])['recipe']
    tool=payload['tool']; strokes=payload.get('strokes',[]);existing_mask=None
    # Refine a cutout against its uncut source, so restore strokes can recover actual pixels.
    if tool=='background' and recipe.get('operations') and recipe['operations'][-1]['tool']=='background':
        old=recipe['operations'][-1]
        prior={**recipe,'operations':recipe['operations'][:-1]}
        original_rgb,original_alpha,meta=imaging.render(path,prior)
        original_rgb,original_alpha=imaging.manual(original_rgb,original_alpha,old.get('adjustments',{}))
        _,existing_alpha,_=imaging.load(store.confined(store.data()/'results',old['result']))
        if existing_alpha is not None:
            _,existing_alpha=imaging.manual(imaging.load(store.confined(store.data()/'results',old['result']))[0],existing_alpha,old.get('adjustments',{}))
            existing_mask=np.frombuffer(existing_alpha.write_to_memory(),np.float32).reshape(existing_alpha.height,existing_alpha.width).copy()
        recipe=prior;rgb,alpha=original_rgb,original_alpha
    else:rgb,alpha,meta=imaging.render(path,recipe)
    # AI needs one evaluated source; sequential decoders cannot be read twice.
    if alpha is not None:
        rgba=rgb.bandjoin(alpha).copy_memory()
        rgb=rgba.extract_band(0,n=3).copy(interpretation='scrgb');alpha=rgba[3]
    else:rgb=rgb.copy_memory()
    pixels=imaging.array(rgb)
    if tool=='background':
        if existing_mask is None:mask=cutout(pixels,ctx,strokes,payload.get('feather',1))
        else:
            mask=existing_mask
            for stroke in strokes:
                patch=imaging.paint_mask([{**stroke,'erase':False}],pixels.shape[1],pixels.shape[0])
                mask=mask*(1-patch) if stroke.get('erase') else mask*(1-patch)+patch
            if payload.get('feather',1):mask=cv2.GaussianBlur(mask,(0,0),float(payload.get('feather',1)))
        if alpha is not None:
            src=np.frombuffer(alpha.write_to_memory(),np.float32).reshape(alpha.height,alpha.width); mask*=src
        background=payload.get('background')
        if background:
            bg=np.array([int(background.lstrip('#')[i:i+2],16) for i in (0,2,4)])
            linear=np.where(bg/255<=.04045,(bg/255)/12.92,((bg/255+.055)/1.055)**2.4)
            matte=pyvips_mask(mask);result=rgb*matte+(1-matte)*linear.tolist();alpha=None
        else:
            alpha=pyvips_mask(mask);result=rgb
    elif tool=='cleanup':
        repaired=imaging.from_array(cleanup(pixels,strokes,ctx,payload.get('feather',3)))
        painted=pyvips_mask((imaging.paint_mask(strokes,pixels.shape[1],pixels.shape[0])>0).astype(np.float32))
        result=painted.ifthenelse(repaired,rgb).copy(interpretation='scrgb')
    elif tool=='enhance':
        scale=int(payload.get('scale',2)); result=imaging.from_array(enhance(pixels,scale,float(payload.get('strength',.5)),ctx))
        if alpha is not None: alpha=alpha.resize(scale)
    else: raise ValueError('Unknown AI tool.')
    ctx.check();store.asset_path(a,payload['revision'])
    filename=store.uid()+'.tif'; dest=store.data()/'results'/filename
    # Float TIFF keeps original precision outside repair regions and in cutout RGB.
    # Model-produced detail is still explicitly disclosed as model precision.
    output=result.copy(interpretation='scrgb').cast('float')
    for key in ['icc-profile-data','exif-data','xmp-data','iptc-data']:
        if output.get_typeof(key):output.remove(key)
    output.set_type(imaging.pyvips.GValue.gint_type,'orientation',1)
    if alpha is not None: output=output.bandjoin(alpha.cast('float'))
    output.write_to_file(str(dest),compression='lzw')
    store.set_setting('result-owner-'+filename,a['id'])
    return {'asset_id':a['id'],'source_revision':a['revision'],'operation':{'tool':tool,'result':filename,'adjustments':{},'precision':'AI processed in sRGB; model detail is not original sensor precision.'},'recipe':recipe}

def pyvips_mask(mask):
    import pyvips
    return pyvips.Image.new_from_memory(mask.astype(np.float32).tobytes(),mask.shape[1],mask.shape[0],1,'float')

def clip_image(a):
    # CLIP uses shortest-side resize followed by a center crop, not aspect distortion.
    h,w=a.shape[:2];s=224/min(h,w);im=Image.fromarray(a).resize((round(w*s),round(h*s)),Image.Resampling.BICUBIC)
    l=(im.width-224)//2;t=(im.height-224)//2
    x=np.asarray(im.crop((l,t,l+224,t+224)),np.float32)/255
    x=(x-np.array([.48145466,.4578275,.40821073],np.float32))/np.array([.26862954,.26130258,.27577711],np.float32)
    return x.transpose(2,0,1)[None].astype(np.float32)

def normalized(vec):
    v=np.asarray(vec,np.float32).flatten();return v/(np.linalg.norm(v)+1e-12)

def image_embedding(a):
    s=session('semantic','onnx/vision_model_quantized.onnx')
    return normalized(infer(s,clip_image(a))[0])

def text_embedding(text):
    from transformers import CLIPTokenizer
    tok=CLIPTokenizer.from_pretrained(str(directory('semantic')),local_files_only=True)
    tokens=tok([text],padding='max_length',max_length=77,truncation=True,return_tensors='np')
    s=session('semantic','onnx/text_model_quantized.onnx')
    args={x.name:tokens[x.name].astype(np.int64) for x in s.get_inputs()}
    return normalized(s.run(None,args)[0])

@functools.lru_cache(maxsize=1)
def face_models():
    d=directory('people')
    return cv2.FaceDetectorYN.create(str(d/'yunet.onnx'),'',(320,320),.85,.3,5000),cv2.FaceRecognizerSF.create(str(d/'sface.onnx'),'')

def faces(a):
    detector,recognizer=face_models(); bgr=cv2.cvtColor(a,cv2.COLOR_RGB2BGR);h,w=a.shape[:2]
    detector.setInputSize((w,h)); detected=detector.detect(bgr)[1]
    result=[]
    for face in detected if detected is not None else []:
        feature=recognizer.feature(recognizer.alignCrop(bgr,face))
        result.append(([float(face[0]/w),float(face[1]/h),float(face[2]/w),float(face[3]/h)],normalized(feature)))
    return result
