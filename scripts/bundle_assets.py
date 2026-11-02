from pathlib import Path
import re,json,xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1]
source=root.parent/'aiko'
metadata={}
for m in re.finditer(r'"([a-f0-9]{6})": \{ name: "([^"]+)"', (source/'index.html').read_text()):metadata.setdefault(m[2],m[1])
sprite=ET.parse(source/'assets'/'icons.svg').getroot()
attrs={n.attrib['id']:n.attrib for n in sprite if 'id' in n.attrib}
(root/'frontend/src/aiko.json').write_text(json.dumps({name:attrs[id] for name,id in metadata.items() if id in attrs}))
shaders=root/'frontend/src/vendor/liquid-glass/shaders'
def expand(path):
 s=path.read_text()
 return re.sub(r'#include\s+[\'\"]([^\'\"]+)[\'\"]',lambda m:expand(path.parent/m[1]),s)
exports=[]
for name,file in [('vertex','vertex.glsl'),('background','fragment-bg.glsl'),('verticalBlur','fragment-bg-vblur.glsl'),('horizontalBlur','fragment-bg-hblur.glsl'),('glass','fragment-main.glsl')]:
 exports.append('export const '+name+' = '+json.dumps(expand(shaders/file))+';')
(root/'frontend/src/vendor/liquid-glass/shaders.ts').write_text('\n'.join(exports))
(root/'frontend/public/licenses/aiko.txt').write_text('Aiko — tw93/aiko\nUpstream README declares MIT License.\nSource revision: 6ae2c093d5bed31096354b72806374ab0848a2db\nhttps://github.com/tw93/aiko\n')
print('Bundled original Aiko symbol attributes and Liquid Glass Studio shaders.')
