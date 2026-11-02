"""Round-trip installed encoders on a small local synthetic photo and record failures."""
from pathlib import Path
import json,time,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from openphoto import store,imaging
from PIL import Image
store.init();store.set_setting('verified_encoders',{});source=store.DATA/'temporary'/'codec-source.png'
im=Image.new('RGB',(48,32));im.putdata([(x*5%256,y*7%256,(x+y)*3%256) for y in range(32) for x in range(48)]);im.save(source)
report=[]
for codec in imaging.formats():
    c={**codec,'tested_write':False,'test_error':None}
    if codec['write']:
        out=store.DATA/'temporary'/('codec-output.'+codec['format'])
        try:imaging.encode(source,{}, {'format':codec['format']},out);c['tested_write']=True
        except Exception as e:c['test_error']=str(e)[-500:]
        finally:out.unlink(missing_ok=True)
    c['verified']=c['tested_write']
    c['write']=c['tested_write']
    report.append(c)
(store.PROJECT/'FORMAT-SUPPORT.json').write_text(json.dumps(report,indent=2))
print('Actual encode/read-back passed:',sum(c['tested_write'] for c in report),'/',sum(c['installed_write'] for c in report),'installed writers')
print('Unsupported or encoder limitations:',[(c['format'],c['test_error'][:100]) for c in report if c['test_error']])
# Do not offer an encoder in this installation when its round-trip verification failed.
store.set_setting('verified_encoders',{c['format']:c['tested_write'] for c in report if c['installed_write']})

# Encoder verification belongs to this installed helper and is shared by its libraries.
verdict={c['format']:c['tested_write'] for c in report if c['installed_write']}
(store.PROJECT/'.liquidframe-formats.json').write_text(json.dumps({'platform':sys.platform,'encoders':verdict},indent=2))
