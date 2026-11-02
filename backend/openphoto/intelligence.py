"""Offline analysis: OCR, object/pet suggestions, frame search, and local collections."""
from pathlib import Path
import csv,io,json,math,datetime,functools
import cv2,numpy as np
from PIL import Image
from . import store,models,imaging,media,jobs,catalog

@functools.lru_cache(maxsize=1)
def labels():return json.loads((models.directory('pets')/'detector/config.json').read_text()).get('id2label',{})

def image_input(pixels,size):
    im=Image.fromarray(pixels[:,:,:3]).resize((size,size),Image.Resampling.BICUBIC)
    values=np.asarray(im).astype(np.float32)/255
    return ((values-np.array([.485,.456,.406],np.float32))/np.array([.229,.224,.225],np.float32)).transpose(2,0,1)[None]

def pets(pixels):
    if not models.installed('pets'):raise ValueError('Download the Pets & object suggestions model pack first.')
    session=models.session('pets','detector/model.onnx');values=image_input(pixels,512);inputs={session.get_inputs()[0].name:values}
    for inp in session.get_inputs()[1:]:inputs[inp.name]=np.ones(tuple(n if isinstance(n,int) else 1 for n in inp.shape),dtype=np.int64)
    result=session.run(None,inputs);mapping={o.name:r for o,r in zip(session.get_outputs(),result)}
    logits=next((r for r in result if r.ndim==3 and r.shape[-1]>4),None);boxes=next((r for r in result if r.ndim==3 and r.shape[-1]==4),None)
    if logits is None or boxes is None:raise ValueError('The detector output is incompatible with this model revision.')
    exp=np.exp(logits[0]-logits[0].max(axis=-1,keepdims=True));prob=exp/exp.sum(axis=-1,keepdims=True);found=[]
    for scores,box in zip(prob,boxes[0]):
        index=int(np.argmax(scores[:-1]));score=float(scores[index]);label=labels().get(str(index),str(index))
        if score<.8:continue
        cx,cy,w,h=map(float,box);left=max(0,cx-w/2);top=max(0,cy-h/2);right=min(1,cx+w/2);bottom=min(1,cy+h/2)
        vector=None
        if label in ['cat','dog']:
            crop=pixels[int(top*pixels.shape[0]):max(int(bottom*pixels.shape[0]),int(top*pixels.shape[0])+1),int(left*pixels.shape[1]):max(int(right*pixels.shape[1]),int(left*pixels.shape[1])+1)]
            sess=models.session('pets','embedding/model.onnx');out=sess.run(None,{sess.get_inputs()[0].name:image_input(crop,224)})[0];vector=out[0,0] if out.ndim==3 else out[0];vector=vector.astype(np.float32);vector/=np.linalg.norm(vector)+1e-9
        found.append({'label':label,'confidence':score,'box':[left,top,right-left,bottom-top],'vector':vector})
    return found

def ocr(asset):
    cached=store.one('SELECT * FROM ocr_regions WHERE asset_id=? AND revision=?',(asset['id'],asset['revision']))
    if cached:return {'text':asset.get('ocr_text',''),'regions':json.loads(cached['regions']),'codes':json.loads(cached['codes'])}
    path=store.asset_path(asset);rgb,_,_=imaging.render(path,{},preview=2048);pixels=imaging.array(rgb);tmp=store.data()/'temporary'/(store.uid()+'.png');Image.fromarray(pixels).save(tmp)
    try:text=media.run('tesseract',[tmp,'stdout','-l','eng','tsv'],120).decode(errors='replace')
    finally:tmp.unlink(missing_ok=True)
    regions=[];lines={}
    for row in csv.DictReader(io.StringIO(text),delimiter='\t',quoting=csv.QUOTE_NONE):
        word=(row.get('text') or '').strip()
        if not word or float(row.get('conf','-1'))<25:continue
        rect=[int(row['left'])/rgb.width,int(row['top'])/rgb.height,int(row['width'])/rgb.width,int(row['height'])/rgb.height]
        regions.append({'text':word,'box':rect,'confidence':float(row['conf'])/100});key=(row['block_num'],row['par_num'],row['line_num']);lines.setdefault(key,[]).append(word)
    codes=[]
    try:
        ok,decoded,points,_=cv2.QRCodeDetector().detectAndDecodeMulti(pixels)
        if ok:codes=[{'text':s,'points':(p/np.array([rgb.width,rgb.height])).tolist()} for s,p in zip(decoded,points)]
    except cv2.error:pass
    value='\n'.join(' '.join(words) for words in lines.values())
    store.asset_path(asset);store.execute('UPDATE assets SET ocr_text=? WHERE id=?',(value,asset['id']));store.execute('INSERT OR REPLACE INTO ocr_regions VALUES(?,?,?,?)',(asset['id'],asset['revision'],json.dumps(regions),json.dumps(codes)))
    return {'text':value,'regions':regions,'codes':codes}

def group_pet(asset,observation):
    vector=observation['vector'];best=None;score=.88
    if vector is None:return None
    reps=store.rows("SELECT person_id,vector FROM observations WHERE kind='pet' AND person_id IS NOT NULL GROUP BY person_id")
    for rep in reps:
        v=np.frombuffer(rep['vector'],np.float32)
        if v.shape!=vector.shape:continue
        similarity=float(v@vector)
        if similarity>score:score=similarity;best=rep['person_id']
    if not best:
        best=store.uid();store.execute("INSERT INTO people(id,name,created,kind) VALUES(?,?,?,'pet')",(best,'Unnamed '+observation['label'],store.now()))
    return best

@jobs.register('extended_analysis')
def analyze(payload,ctx):
    kinds=payload.get('kinds',[])
    if set(kinds)-{'semantic','people','duplicates','ocr','pets','curation','video'}:raise ValueError('Unknown analysis type.')
    common=[k for k in kinds if k in ['semantic','people','duplicates']]
    if common:
        from .library import analyze as original
        original({'kinds':common},ctx)
    if 'pets' in kinds:models.ensure('pets',ctx)
    if 'video' in kinds:models.ensure('semantic',ctx)
    with store.db() as c:c.execute('CREATE TABLE IF NOT EXISTS analysis_state(asset_id TEXT,kind TEXT,revision INTEGER,PRIMARY KEY(asset_id,kind))')
    offset=0;processed=0;errors=[];total=store.one('SELECT COUNT(*) n FROM assets WHERE '+catalog.visibility())['n']
    while True:
        chunk=store.rows('SELECT id FROM assets WHERE '+catalog.visibility()+" AND status='ready' ORDER BY id LIMIT 100 OFFSET ?",(offset,))
        if not chunk:break
        for row in chunk:
            ctx.progress(processed/max(total,1)*.95,f'Analyzing {processed+1:,}/{total:,} items');processed+=1
            try:
                a=store.get_asset(row['id']);path=store.asset_path(a)
                needed=[k for k in kinds if not store.one('SELECT asset_id FROM analysis_state WHERE asset_id=? AND kind=? AND revision=?',(a['id'],k,a['revision']))]
                if 'ocr' in needed:ocr(a)
                if 'pets' in needed:
                    rgb,_,_=imaging.render(path,{},preview=1024);observations=pets(imaging.array(rgb));store.execute("DELETE FROM observations WHERE asset_id=? AND kind IN ('pet','object')",(a['id'],))
                    for o in observations:
                        person=group_pet(a,o);v=o['vector'];store.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?)',(store.uid(),a['id'],a['revision'],'pet' if person else 'object',o['label'],json.dumps(o['box']),v.tobytes() if v is not None else None,0,person))
                if 'video' in needed and a['media_kind']=='video':
                    times=np.linspace(0,max(0,a['duration']-.1),min(600,max(1,int(a['duration']/5))))
                    for t in times:
                        ctx.check();p=media.frame(path,float(t),512);rgb,_,_=imaging.load(p);vec=models.image_embedding(imaging.array(rgb));store.execute('INSERT OR REPLACE INTO frame_search VALUES(?,?,?,?,?)',(a['id'],a['revision'],float(t),vec.tobytes(),''))
                if 'curation' in needed:
                    rgb,_,_=imaging.render(path,{},preview=256);pix=imaging.array(rgb);gray=cv2.cvtColor(pix,cv2.COLOR_RGB2GRAY);quality=float(cv2.Laplacian(gray,cv2.CV_32F).var())*(1-abs(float(gray.mean())-128)/128);store.execute('UPDATE assets SET quality=? WHERE id=?',(quality,a['id']))
                for k in needed:store.execute('INSERT OR REPLACE INTO analysis_state VALUES(?,?,?)',(a['id'],k,a['revision']))
            except jobs.Cancelled:raise
            except Exception as e:
                if len(errors)<100:errors.append({'asset_id':row['id'],'error':str(e)})
        offset+=len(chunk)
    if 'curation' in kinds:curate()
    return {'processed':processed,'errors':errors}

def curate():
    """Date/place grouping, informed by OwnPhotos event albums; no geocoding requests."""
    groups={}
    excluded={r['asset_id'] for r in store.rows('SELECT f.asset_id FROM faces f JOIN people p ON p.id=f.person_id WHERE p.feature_less=1 OR p.hidden=1 UNION SELECT o.asset_id FROM observations o JOIN people p ON p.id=o.person_id WHERE p.feature_less=1 OR p.hidden=1')}
    for a in store.rows('SELECT id,captured,place,latitude,longitude,quality,favorite,rating FROM assets WHERE '+catalog.visibility()+" AND status='ready' ORDER BY captured"):
        if a['id'] in excluded:continue
        day=(a['captured'] or '')[:10]
        if not day:continue
        place=a['place'] or ''
        key=(day,place);groups.setdefault(key,[]).append(a)
    for (day,place),items in groups.items():
        if len(items)<2:continue
        date=datetime.date.fromisoformat(day);name=(place+' · ' if place else '')+date.strftime('%B %-d, %Y') if __import__('os').name!='nt' else (place+' · ' if place else '')+date.isoformat()
        key=__import__('hashlib').sha256(('event:'+day+place).encode()).hexdigest()[:32];ids=[a['id'] for a in items]
        store.execute("INSERT INTO collections(id,kind,name,assets,created) VALUES(?,'memories',?,?,?) ON CONFLICT(id) DO UPDATE SET assets=excluded.assets",(key,name,json.dumps(ids),store.now()))
        if place and len(items)>=3:
            trip=__import__('hashlib').sha256(('trip:'+day+place).encode()).hexdigest()[:32];store.execute("INSERT INTO collections(id,kind,name,assets,created) VALUES(?,'trips',?,?,?) ON CONFLICT(id) DO UPDATE SET assets=excluded.assets",(trip,name,json.dumps(ids),store.now()))
    top=store.rows('SELECT id FROM assets WHERE '+catalog.visibility()+" AND status='ready' AND media_kind='photo' ORDER BY favorite DESC,rating DESC,quality DESC LIMIT 50")
    store.execute("INSERT INTO collections(id,kind,name,assets,created) VALUES('featured','featured','Featured photos',?,?) ON CONFLICT(id) DO UPDATE SET assets=excluded.assets",(json.dumps([a['id'] for a in top]),store.now()))

def suggestions(q):
    result=[]
    if not q.strip():return []
    for label,col,key in [('Place','place','place'),('Camera','camera','camera'),('Keyword','keywords','keyword')]:
        rows=store.rows('SELECT '+col+' value,COUNT(*) count FROM assets WHERE '+catalog.visibility()+' AND '+col+" LIKE ? AND "+col+"!='' GROUP BY "+col+' LIMIT 5',('%'+q+'%',))
        for r in rows:result.append({'label':f'{label}: {r["value"]}','count':r['count'],'filter':{'conditions':[{'field':key,'operator':'contains','value':r['value']}]}})
    people=store.rows('SELECT id,name FROM people WHERE hidden=0 AND name LIKE ? LIMIT 5',('%'+q+'%',))
    for p in people:
        count=catalog.query({'person_id':p['id']},0,1)['total']
        if count:result.append({'label':p['name'],'count':count,'filter':{'person_id':p['id']}})
    if len(q)==4 and q.isdigit():result.insert(0,{'label':q,'count':catalog.query({'date_from':q+'-01-01','date_to':q+'-12-31'},0,1)['total'],'filter':{'date_from':q+'-01-01','date_to':q+'-12-31'}})
    return result
