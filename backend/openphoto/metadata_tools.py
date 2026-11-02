"""Source metadata and sidecars stay separate from catalog overrides."""
from pathlib import Path
import json,re,xml.etree.ElementTree as ET
from . import store,media

def read(path):
    if not media.executable('exiftool'):return {}
    rows=json.loads(media.run('exiftool',['-json','-n','-G1',str(path)],30));return rows[0] if rows else {}

def enrich(asset_id,path,meta):
    def val(*keys):
        for k in keys:
            for key,value in meta.items():
                if k.lower() in key.lower():return value
        return None
    def number(v):
        try:return float(str(v).split(' ')[0])
        except (ValueError,TypeError):return None
    if path.suffix.lower() in ['.heic','.heif','.mov'] and media.executable('exiftool'):
        try:
            extracted=read(path)
            identifiers={k:v for k,v in extracted.items() if any(t in k.lower() for t in ['identifier','burstuuid','gpslatitude','gpslongitude','portrait','cinematic','contentidentifier'])}
            meta.update(identifiers);store.execute('UPDATE assets SET metadata=? WHERE id=?',(json.dumps(meta),asset_id))
        except Exception:pass
    lat=number(val('gpslatitude'));lon=number(val('gpslongitude'))
    if lat is not None and lon is not None:
        if str(val('gpslatituderef') or '').startswith('S'):lat=-abs(lat)
        if str(val('gpslongituderef') or '').startswith('W'):lon=-abs(lon)
        store.execute('UPDATE assets SET latitude=COALESCE(latitude,?),longitude=COALESCE(longitude,?) WHERE id=?',(lat,lon,asset_id))
    store.execute('UPDATE assets SET camera=?,lens=?,iso=?,aperture=?,focal_length=?,shutter=? WHERE id=?',(str(val('model') or ''),str(val('lensmodel') or ''),number(val('isospeed','iso')),number(val('fnumber')),number(val('focallength')),number(val('exposuretime')),asset_id))
    for ext in ['.xmp','.XMP','.aae','.AAE','.slm']:
        for p in [path.with_suffix(ext),Path(str(path)+ext)]:
            if not p.is_file() or p.is_symlink():continue
            store.execute('INSERT OR REPLACE INTO sidecars VALUES(?,?,?,?)',(asset_id,str(p),ext[1:].lower(),p.stat().st_mtime_ns))
            if ext.lower()=='.xmp':
                if p.stat().st_size>5_000_000:continue
                content=p.read_bytes()
                if b'<!DOCTYPE' in content or b'<!ENTITY' in content:continue
                try:
                    tree=ET.fromstring(content);title='';caption='';keywords=[];rating=None
                    for element in tree.iter():
                        tag=element.tag.split('}')[-1].lower()
                        if tag=='title':title=' '.join(element.itertext()).strip()
                        if tag=='description':caption=' '.join(element.itertext()).strip()
                        if tag=='subject':keywords=[s.text for s in element.iter() if s.tag.endswith('}li') and s.text]
                        for k,v in element.attrib.items():
                            if k.endswith('}Rating'):rating=min(5,max(0,int(v)))
                    old=store.one('SELECT title,caption,keywords,rating FROM assets WHERE id=?',(asset_id,))
                    store.execute('UPDATE assets SET title=?,caption=?,keywords=?,rating=? WHERE id=?',(old['title'] or title,old['caption'] or caption,old['keywords'] if old['keywords']!='[]' else json.dumps(keywords),old['rating'] or rating or 0,asset_id))
                except (ET.ParseError,ValueError):continue

def xmp(asset):
    ns={'x':'adobe:ns:meta/','rdf':'http://www.w3.org/1999/02/22-rdf-syntax-ns#','dc':'http://purl.org/dc/elements/1.1/','xmp':'http://ns.adobe.com/xap/1.0/'}
    for k,v in ns.items():ET.register_namespace(k,v)
    root=ET.Element('{'+ns['x']+'}xmpmeta');rdf=ET.SubElement(root,'{'+ns['rdf']+'}RDF');desc=ET.SubElement(rdf,'{'+ns['rdf']+'}Description',{'{'+ns['xmp']+'}Rating':str(asset.get('rating',0))})
    for key,value in [('title',asset.get('title','')),('description',asset.get('caption',''))]:
        node=ET.SubElement(desc,'{'+ns['dc']+'}'+key);alt=ET.SubElement(node,'{'+ns['rdf']+'}Alt');ET.SubElement(alt,'{'+ns['rdf']+'}li',{'{http://www.w3.org/XML/1998/namespace}lang':'x-default'}).text=value
    node=ET.SubElement(desc,'{'+ns['dc']+'}subject');bag=ET.SubElement(node,'{'+ns['rdf']+'}Bag')
    for k in asset.get('keywords',[]):ET.SubElement(bag,'{'+ns['rdf']+'}li').text=k
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)

def associate(root_id):
    """Pair only verified content IDs, RAW/JPEG basenames, and explicit burst IDs."""
    from . import catalog,imaging
    groups={};raw={}
    rows=store.rows('SELECT id,name,relative_path,extension,metadata,stack_id FROM assets WHERE root_id=? AND purged=0',(root_id,))
    for a in rows:
        if a['stack_id']:continue
        meta=json.loads(a['metadata']);identifier=next((str(v).strip() for k,v in meta.items() if any(t in k.lower().replace('-','') for t in ['contentidentifier','assetidentifier']) and v),None)
        tags=meta.get('tags',{})
        if not identifier:identifier=next((str(v) for k,v in tags.items() if 'content.identifier' in k.lower()),None)
        burst=next((str(v) for k,v in meta.items() if 'burstuuid' in k.lower() and v),None)
        if identifier:groups.setdefault(('live',identifier),[]).append(a)
        if burst:groups.setdefault(('burst',burst),[]).append(a)
        if a['extension'] in imaging.RAW or a['extension'] in ['jpg','jpeg']:raw.setdefault(str(Path(a['relative_path']).with_suffix('')).casefold(),[]).append(a)
    for key,items in raw.items():
        if any(a['extension'] in imaging.RAW for a in items) and any(a['extension'] in ['jpg','jpeg'] for a in items):groups[('raw_jpeg',key)]=items
    for (kind,key),items in groups.items():
        if len(items)<2:continue
        if kind=='live' and not any(a['extension'] in media.VIDEO for a in items):continue
        primary=next((a for a in items if a['extension'] not in media.VIDEO and a['extension'] not in imaging.RAW),items[0])
        catalog.stack({'ids':[a['id'] for a in items]},kind,primary['id'])
