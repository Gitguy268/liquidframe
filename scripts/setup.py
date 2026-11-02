#!/usr/bin/env python3
"""Build the local frontend and install isolated project dependencies."""
import argparse,hashlib,json,os,shutil,subprocess,sys,venv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def run(args,**kwargs):subprocess.run(args,cwd=ROOT,check=True,**kwargs)
def setup_signature():
    inputs=[ROOT/name for name in ['pyproject.toml','frontend/package-lock.json','scripts/setup.py','scripts/build-photobook.mjs','companions/photobook/package-lock.json','companions/photobook/next.config.js','companions/photobook/LIQUIDFRAME.md','companions/photobook/LICENSE']]
    for folder in ['backend','frontend/src','companions/photobook/src','companions/photobook/public']:
        inputs.extend(p for p in sorted((ROOT/folder).rglob('*')) if p.is_file() and '__pycache__' not in p.parts)
    return hashlib.sha256(b''.join(p.read_bytes() for p in inputs)).hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--force',action='store_true');args=parser.parse_args()
    if sys.version_info<(3,11):raise SystemExit('LiquidFrame requires Python 3.11 or later. Install Python from python.org and run this script with that interpreter.')
    env=ROOT/'.venv';python=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    signature=setup_signature()
    marker=env/'openphoto-setup.json'
    if not args.force and python.exists() and marker.exists() and json.loads(marker.read_text()).get('signature')==signature and (ROOT/'frontend/dist/index.html').exists() and (ROOT/'companions/photobook/out/index.html').exists():return
    if not python.exists():venv.create(env,with_pip=True)
    npm=shutil.which('npm.cmd' if os.name=='nt' else 'npm')
    if not npm:raise SystemExit('Install Node.js LTS from nodejs.org, then run setup again. Node is used only to build the interface.')
    if sys.platform in ['linux','win32']:
        run([str(python),'-m','pip','install','torch>=2.6,<3','--index-url','https://download.pytorch.org/whl/cpu'])
    run([str(python),'-m','pip','install','-e',str(ROOT)])
    subprocess.run([npm,'ci','--ignore-scripts'],cwd=ROOT/'frontend',check=True)
    run([str(python),'scripts/collect_web_licenses.py'])
    subprocess.run([npm,'run','build'],cwd=ROOT/'frontend',check=True)
    run([shutil.which('node'),'scripts/build-photobook.mjs'])
    if not shutil.which('magick'):print('ImageMagick is optional for extra formats. macOS: brew install imagemagick; Windows: install from imagemagick.org; Linux: install ImageMagick 7 from your distribution.')
    if not shutil.which('cjxl'):print('JPEG XL: optionally install cjxl/djxl from libjxl. macOS: brew install jpeg-xl.')
    missing=[tool for tool in ['ffmpeg','ffprobe','tesseract','exiftool'] if not shutil.which(tool)]
    if missing:print('Optional local tools not on PATH: '+', '.join(missing)+'. See README platform instructions. Video/OCR/metadata tools remain unavailable until installed.')
    run([str(python),'scripts/verify_formats.py'])
    marker.write_text(json.dumps({'signature':signature}))
    print('Ready. Launch LiquidFrame with the start script for your operating system.')
if __name__=='__main__':main()
