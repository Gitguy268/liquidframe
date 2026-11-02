import urllib.request
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'frontend/public/licenses'
sources={
'real-esrgan.txt':'https://raw.githubusercontent.com/xinntao/Real-ESRGAN/master/LICENSE',
'birefnet.txt':'https://raw.githubusercontent.com/ZhengPeng7/BiRefNet/main/LICENSE',
'clip.txt':'https://raw.githubusercontent.com/openai/CLIP/main/LICENSE',
'yunet.txt':'https://raw.githubusercontent.com/opencv/opencv_zoo/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_detection_yunet/LICENSE',
'sface.txt':'https://raw.githubusercontent.com/opencv/opencv_zoo/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_recognition_sface/LICENSE',
'lama.txt':'https://raw.githubusercontent.com/advimman/lama/main/LICENSE',
}
for name,url in sources.items():
 try:(p/name).write_bytes(urllib.request.urlopen(url,timeout=30).read());print('Saved',name)
 except Exception as e:print(name,e)
import json
items=json.load(urllib.request.urlopen('https://api.github.com/repos/letmaik/rawpy/contents/test'))
print('RAW test assets:',[(x['name'],x['size'],x.get('download_url')) for x in items if x['name'].lower().endswith(('.nef','.cr2','.dng','.arw'))])
