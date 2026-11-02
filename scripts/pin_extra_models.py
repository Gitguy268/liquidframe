"""Maintainer: resolve immutable ONNX conversions and record content checksums."""
import urllib.request,json,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1];manifest=json.loads((root/'backend/openphoto/models.json').read_text());files=[]
for repo,prefix in [('Xenova/detr-resnet-50','detector'),('Xenova/dinov2-small','embedding')]:
 request=urllib.request.Request('https://huggingface.co/api/models/'+repo,headers={'User-Agent':'LiquidFrame'})
 info=json.load(urllib.request.urlopen(request));rev=info['sha'];names=[s['rfilename'] for s in info['siblings']]
 name='onnx/model_quantized.onnx' if 'onnx/model_quantized.onnx' in names else 'onnx/model.onnx'
 for filename in [name,'config.json','preprocessor_config.json']:
  url=f'https://huggingface.co/{repo}/resolve/{rev}/{filename}'
  # Xet object IDs are not content SHA-256; hash the actual immutable file.
  data=urllib.request.urlopen(url).read();digest=hashlib.sha256(data).hexdigest();size=len(data)
  files.append({'url':url,'name':prefix+'/'+('model.onnx' if filename.endswith('.onnx') else filename),'sha256':digest,'size':size})
 print(repo,rev,flush=True)
manifest['pets']={'label':'Pets & object suggestions','license':'Apache-2.0','source':'https://github.com/facebookresearch/detr; https://github.com/facebookresearch/dinov2','files':files}
(root/'backend/openphoto/models.json').write_text(json.dumps(manifest,indent=2)+'\n')
