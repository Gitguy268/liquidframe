"""Real inference check using a public-domain NASA sample, never a user's photo."""
from pathlib import Path
import json,sys,urllib.request,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from openphoto import store,models,imaging,library
import numpy as np,cv2
class C:
    id='smoke';last=''
    def check(self):pass
    def progress(self,v,message):
        label=message.split(' · ')[0]
        if label!=self.last:print(label,flush=True);self.last=label
ctx=C();store.init()
for key in models.MANIFEST:
    started=time.perf_counter();models.ensure(key,ctx,0,1);print(key,'verified',round(time.perf_counter()-started,1),'s',flush=True)
sample=store.DATA/'temporary'/'astronaut.png'
if not sample.exists():
    sample.write_bytes(urllib.request.urlopen('https://raw.githubusercontent.com/scikit-image/scikit-image/v0.25.2/skimage/data/astronaut.png').read())
class NoNetwork:
    def __init__(self,*a,**k):raise AssertionError('Unexpected network access')
models.httpx.Client=NoNetwork
rgb,_,_=imaging.render(sample,{},preview=256);a=imaging.array(rgb)
report={}
start=time.perf_counter();mask=models.cutout(a,ctx);assert mask.shape==a.shape[:2] and mask.max()>.5;report['background_seconds']=time.perf_counter()-start
strokes=[{'points':[[.7,.7],[.75,.72]],'radius':.025}]
start=time.perf_counter();clean=models.cleanup(a,strokes,ctx);m=imaging.paint_mask(strokes,a.shape[1],a.shape[0]);assert np.array_equal(clean[m==0],a[m==0]);report['cleanup_seconds']=time.perf_counter()-start
start=time.perf_counter();enhanced=models.enhance(cv2.resize(a,(64,64)),2,.5,ctx);assert enhanced.shape==(128,128,3);report['enhance_seconds']=time.perf_counter()-start
start=time.perf_counter();v=models.image_embedding(a);t=models.text_embedding('an astronaut');assert v.shape==t.shape==(512,);assert abs(float(np.linalg.norm(v))-1)<.001;report['semantic_seconds']=time.perf_counter()-start;report['clip_similarity']=float(v@t)
start=time.perf_counter();f=models.faces(a);assert len(f)>=1;report['faces']=len(f);report['people_seconds']=time.perf_counter()-start
# Once cached, all operations must complete without a network-capable client.
class NoNetwork:
    def __init__(self,*a,**k):raise AssertionError('Unexpected network access')
models.httpx.Client=NoNetwork
for key in models.MANIFEST:models.ensure(key,ctx)
report['cached_models_offline']=True
(store.PROJECT/'AI-VERIFICATION.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2),flush=True)
