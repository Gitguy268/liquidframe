"""Maintainer-only: record immutable public model assets; no user photos are read."""
import hashlib,json,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
manifest={}
def file(url,name,sha=None,size=None,content=False):
    if sha is None:
        b=urllib.request.urlopen(url,timeout=60).read(); sha=hashlib.sha256(b).hexdigest();size=len(b)
        if content:
            p=ROOT/'.openphoto-data'/'models'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
    return {'url':url,'name':name,'sha256':sha,'size':size}
def hf(repo,rev,names):
    d=json.load(urllib.request.urlopen('https://huggingface.co/api/models/'+repo+'?blobs=true'))
    assert d['sha']==rev
    out=[]
    for name in names:
        s=next(s for s in d['siblings'] if s['rfilename']==name)
        out.append(file(f'https://huggingface.co/{repo}/resolve/{rev}/{name}',name,s.get('lfs',{}).get('sha256'),s.get('size')))
    return out
manifest['background']={'label':'Background removal','license':'MIT','source':'https://github.com/ZhengPeng7/BiRefNet','files':hf('onnx-community/BiRefNet_lite-ONNX','de15b22ba131738a16dff04aab8bdf8dc32e3ac1',['onnx/model.onnx','preprocessor_config.json'])}
manifest['cleanup']={'label':'Object cleanup','license':'Apache-2.0','source':'https://huggingface.co/Carve/LaMa-ONNX','files':hf('Carve/LaMa-ONNX','c3c0c9e468934d62e79c329e35d82dd09ff8c444',['lama_fp32.onnx'])}
manifest['semantic']={'label':'Semantic search','license':'MIT (upstream CLIP weights)','source':'https://github.com/openai/CLIP','files':hf('Xenova/clip-vit-base-patch32','d15189d7028b43f1d3e65039190477f6af591c2a',['onnx/vision_model_quantized.onnx','onnx/text_model_quantized.onnx','vocab.json','merges.txt','tokenizer_config.json','special_tokens_map.json','preprocessor_config.json','config.json'])}
rev='47534e27c9851bb1128ccc0102f1145e27f23f98'
manifest['people']={'label':'People grouping','license':'YuNet MIT; SFace Apache-2.0','source':'https://github.com/opencv/opencv_zoo','files':[
file(f'https://media.githubusercontent.com/media/opencv/opencv_zoo/{rev}/models/face_detection_yunet/face_detection_yunet_2023mar.onnx','yunet.onnx','8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4',232589),
file(f'https://media.githubusercontent.com/media/opencv/opencv_zoo/{rev}/models/face_recognition_sface/face_recognition_sface_2021dec.onnx','sface.onnx','0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79',38696353)]}
manifest['enhance']={'label':'Restore & upscale','license':'BSD-3-Clause','source':'https://github.com/xinntao/Real-ESRGAN','files':[
file('https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/'+n,n) for n in ['realesr-general-x4v3.pth','realesr-general-wdn-x4v3.pth']]}
(ROOT/'backend'/'openphoto'/'models.json').write_text(json.dumps(manifest,indent=2))
print('Pinned',sum(len(v['files']) for v in manifest.values()),'assets;',round(sum(f['size'] for v in manifest.values() for f in v['files'])/1e6),'MB total')
