"""Collect installed production dependency notices for the locally bundled UI."""
from pathlib import Path
import json,re,shutil
ROOT=Path(__file__).resolve().parents[1]
lock=json.loads((ROOT/'frontend/package-lock.json').read_text())
destination=ROOT/'frontend/public/licenses/npm';destination.mkdir(parents=True,exist_ok=True)
report=[]
for location,entry in lock.get('packages',{}).items():
    if not location or entry.get('dev'):continue
    directory=ROOT/'frontend'/location
    if not (directory/'package.json').exists():continue
    package=json.loads((directory/'package.json').read_text());name=package.get('name',location)
    item={'name':name,'version':package.get('version'),'license':package.get('license'),'notices':[]}
    for file in directory.iterdir():
        if not file.is_file() or not re.match(r'^(licen[cs]e|copying|notice)(\..*)?$',file.name,re.I):continue
        target=re.sub(r'[^a-zA-Z0-9._-]','_',name)+'-'+str(package.get('version'))+'-'+file.name
        shutil.copyfile(file,destination/target);item['notices'].append(target)
    if not item['notices']:
        for readme in directory.glob('README*'):
            text=readme.read_text(errors='replace');section=re.search(r'^#+\s+Licen[cs]e.*$',text,re.M|re.I)
            if section:
                target=re.sub(r'[^a-zA-Z0-9._-]','_',name)+'-'+str(package.get('version'))+'-README-license.txt'
                (destination/target).write_text(text[section.start():]);item['notices'].append(target);break
    report.append(item)
(destination/'index.json').write_text(json.dumps(report,indent=2))
print(f'Bundled license metadata for {len(report)} production packages; '+str(sum(len(i['notices']) for i in report))+' notice files.')
