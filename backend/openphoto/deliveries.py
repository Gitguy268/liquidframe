"""New-copy batch exports, slideshow projects, and local print documents."""
from pathlib import Path
import datetime,hashlib,json,math,os,re,shutil,subprocess,wave
import numpy as np
from . import store,jobs,catalog,media,imaging,metadata_tools


def filename(asset,options,sequence):
    date=datetime.datetime.fromisoformat(asset['captured'].replace('Z','+00:00')) if asset.get('captured') else datetime.datetime.now()
    values={'original':Path(asset['name']).stem,'title':asset.get('title') or Path(asset['name']).stem,'year':date.strftime('%Y'),'month':date.strftime('%m'),'day':date.strftime('%d'),'date':date.strftime('%Y-%m-%d'),'sequence':f'{sequence:04d}'}
    template=options.get('template','{original}-edited')
    for key,value in values.items():template=template.replace('{'+key+'}',str(value))
    if '{' in template or '}' in template:raise ValueError('Unknown filename token.')
    template=re.sub(r'[\\/<>:"|?*\x00-\x1f]','_',template).strip(' .')[:200]
    return template or values['original']

def destination(root,asset,options,sequence,extension):
    parent=Path()
    if options.get('subfolders')=='source':parent=Path(asset['relative_path']).parent
    elif options.get('subfolders')=='date':parent=Path((asset.get('captured') or 'undated')[:10])
    name=filename(asset,options,sequence);p=store.confined(root,str(parent/(name+'.'+extension)),False);p.parent.mkdir(parents=True,exist_ok=True);n=1
    while p.exists():p=store.confined(root,str(parent/(name+f'-{n}.'+extension)),False);n+=1
    return p

@jobs.register('batch_export')
def batch_export(payload,ctx):
    selected=catalog.ids(payload['selection']);root=store.root_path(payload['output_root']);options=payload.get('options',{});original=payload.get('mode')=='original';items=[];seen=set()
    for i in selected:
        a=store.get_asset(i);group=[i]
        if original and a.get('stack_id'):group=[r['id'] for r in store.rows('SELECT id FROM assets WHERE stack_id=?',(a['stack_id'],))]
        for component in group:
            if component not in seen:store.get_asset(component);items.append(component);seen.add(component)
    files=[];errors=[];completed=0
    for n,i in enumerate(items):
        ctx.progress(n/max(1,len(items)),f'Exporting {n+1:,}/{len(items):,} items');temp=None
        previous=store.one('SELECT * FROM export_items WHERE job_id=? AND asset_id=? AND error IS NULL',(ctx.id,i))
        if previous:completed+=1;continue
        try:
            a=store.get_asset(i);expected=store.one('SELECT revision FROM selection_items WHERE selection_id=? AND asset_id=?',(payload['selection'].get('selection_id',''),i))
            if expected and expected['revision']!=a['revision']:raise ValueError('Source changed after selection. Select it again before exporting.')
            path=store.asset_path(a,payload.get('revisions',{}).get(i,a['revision']));extension=path.suffix[1:] if original else 'mp4' if a['media_kind']=='video' else options.get('format','jpg')
            out=destination(root,a,options,n+1,extension);temp=out.with_name('.'+store.uid()+'.'+extension)
            if original:
                before=store.digest(path);shutil.copyfile(path,temp)
                if store.digest(temp)!=before or store.digest(path)!=before:raise ValueError('Original copy failed verification.')
            elif a['media_kind']=='video':media.render_video(path,store.get_recipe(i)['recipe'],options,temp,ctx)
            else:
                imaging.encode(path,store.get_recipe(i)['recipe'],{**options,'format':extension,'strip_metadata':not options.get('metadata',True)},temp)
                if media.executable('exiftool'):
                    args=['-overwrite_original']
                    if not options.get('location',True):args+=['-GPS:All=']
                    if options.get('metadata',True) and extension not in ['gif','apng']:
                        args+=['-XMP-dc:Title='+a.get('title',''),'-XMP-dc:Description='+a.get('caption',''),'-XMP-xmp:Rating='+str(a.get('rating',0))]
                        for keyword in a.get('keywords',[]):args.append('-XMP-dc:Subject+='+keyword)
                    if len(args)>1:media.run('exiftool',[*args,temp])
                imaging.verify_output(temp,extension)
            ctx.check();store.asset_path(a,a['revision']);os.replace(temp,out);temp=None
            if options.get('xmp'):
                side=out.with_suffix(out.suffix+'.xmp');side.write_bytes(metadata_tools.xmp(a))
            if original:
                for side in store.rows('SELECT path FROM sidecars WHERE asset_id=?',(i,)):
                    p=Path(side['path']);source=store.confined(store.root_path(a['root_id']),str(p.relative_to(store.root_path(a['root_id']))))
                    target=out.with_name(out.stem+source.suffix)
                    if not target.exists():shutil.copy2(source,target)
            store.execute('UPDATE assets SET exported_at=? WHERE id=?',(store.now(),i));store.execute('INSERT OR REPLACE INTO export_items VALUES(?,?,?,NULL,NULL)',(ctx.id,i,str(out)))
            completed+=1
            if len(files)<200:files.append({'path':str(out)})
        except jobs.Cancelled:raise
        except Exception as e:
            if len(errors)<100:errors.append({'asset_id':i,'error':str(e)})
            store.execute('INSERT OR REPLACE INTO export_items VALUES(?,?,NULL,NULL,?)',(ctx.id,i,str(e)))
        finally:
            if temp:temp.unlink(missing_ok=True)
    if errors and not completed:raise ValueError(errors[0]['error'])
    return {'files':files,'file_count':completed,'errors':errors}


def project_allowed(project):
    from .workspaces import PRIVATE
    doc=json.loads(project['document']) if isinstance(project['document'],str) else project['document']
    if doc.get('_private') and not PRIVATE.get():raise PermissionError('Unlock private views to access this project.')
    for i in doc.get('asset_ids',[]):store.get_asset(i)
    return doc

def create_project(name,kind,selection):
    from .workspaces import PRIVATE
    chosen=catalog.ids(selection)
    if len(chosen)>500:raise ValueError('A project can contain up to 500 items. Narrow the selection first.')
    for i in chosen:store.get_asset(i)
    i=store.uid();document={'asset_ids':chosen,'duration':4,'transition':'fade','motion':'gentle','fit':'fit','music':'none','look':'Original','_private':PRIVATE.get()};now=store.now()
    store.execute('INSERT INTO projects VALUES(?,?,?,?,?,?)',(i,kind,name[:150],json.dumps(document),now,now));return {'id':i,'name':name,'kind':kind,'document':document}

def gentle_music(path,duration):
    # Original deterministic instrumental, synthesized locally; no third-party audio.
    rate=22050;n=int(rate*duration)
    with wave.open(str(path),'wb') as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(rate)
        for start in range(0,n,rate*4):
            count=min(rate*4,n-start);t=np.arange(count)/rate;note=[220,261.6256,329.6276,293.6648][(start//(rate*4))%4];envelope=np.minimum(1,t/.4)*np.exp(-t/.9);value=(np.sin(2*np.pi*note*t)+.35*np.sin(2*np.pi*note*2*t)+.2*np.sin(2*np.pi*note*1.5*t))*envelope*.12
            out.writeframes((value*32767).astype('<i2').tobytes())

@jobs.register('project_export')
def project_export(payload,ctx):
    from .adjustments import LOOKS
    p=store.one('SELECT * FROM projects WHERE id=?',(payload['project_id'],))
    if not p:raise ValueError('Project not found.')
    doc=project_allowed(p);items=doc.get('asset_ids',[])
    if not items:raise ValueError('Add media to this project first.')
    duration=max(1,min(60,float(doc.get('duration',4))));root=store.root_path(payload['output_root']);out=store.confined(root,re.sub(r'[^\w .-]','_',p['name'])+'.mp4',False);n=1
    while out.exists():out=store.confined(root,re.sub(r'[^\w .-]','_',p['name'])+f'-{n}.mp4',False);n+=1
    folder=store.data()/'temporary'/('project-'+store.uid());folder.mkdir();segments=[];target=out.with_name('.'+store.uid()+'.mp4')
    try:
        for index,i in enumerate(items):
            ctx.progress(index/len(items)*.8,f'Rendering slide {index+1}/{len(items)}');a=store.get_asset(i);path=store.asset_path(a);segment=folder/f'{index:05d}.mp4'
            if a['media_kind']=='video':
                media.process(['-i',path,'-t',duration,'-vf','scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30','-an','-c:v','libx264','-pix_fmt','yuv420p',segment],ctx,duration)
            else:
                recipe=store.get_recipe(i)['recipe'].copy();recipe['adjustments']={**recipe.get('adjustments',{}),**LOOKS.get(doc.get('look','Original'),{})};still=folder/f'{index:05d}.png';imaging.encode(path,recipe,{'format':'png'},still)
                fit='increase' if doc.get('fit')=='fill' else 'decrease';vf=f'scale=1920:1080:force_original_aspect_ratio={fit},'+('crop=1920:1080' if fit=='increase' else 'pad=1920:1080:(ow-iw)/2:(oh-ih)/2')
                if doc.get('motion')!='none':vf+=f",zoompan=z='min(zoom+0.00035,1.06)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={int(duration*30)}:s=1920x1080:fps=30"
                if doc.get('transition')=='fade':vf+=f',fade=t=in:st=0:d=0.35,fade=t=out:st={duration-.35}:d=0.35'
                media.process(['-loop','1','-i',still,'-t',duration,'-vf',vf+',setsar=1','-an','-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p',segment],ctx,duration)
            segments.append(segment)
        listing=folder/'concat.txt';listing.write_text(''.join("file '"+str(segment)+"'\n" for segment in segments));args=['-f','concat','-safe','0','-i',listing]
        if doc.get('music')=='gentle':
            audio=folder/'music.wav';gentle_music(audio,duration*len(items));args+=['-i',audio,'-c:a','aac','-shortest']
        args+=['-c:v','copy','-movflags','+faststart',target];media.process(args,ctx,duration*len(items));media.probe(target);os.replace(target,out)
    finally:target.unlink(missing_ok=True);shutil.rmtree(folder,ignore_errors=True)
    return {'files':[{'path':str(out)}]}

def print_pdf(selection,options):
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.pagesizes import A4,letter,landscape
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import reportlab
    chosen=catalog.ids(selection)
    if len(chosen)>5000:raise ValueError('Print at most 5,000 items at once.')
    uid=store.uid();out=store.data()/'results'/(uid+'.pdf');size=letter if options.get('paper')=='Letter' else A4
    sizes={'4x6':(288,432),'5x7':(360,504),'8x10':(576,720),'10x15cm':(283.465,425.197),'13x18cm':(368.504,510.236),'20x25cm':(566.929,708.661)}
    size=sizes.get(options.get('paper'),size)
    if options.get('paper')=='custom':size=(max(72,min(4320,float(options.get('width_mm',210))*72/25.4)),max(72,min(4320,float(options.get('height_mm',297))*72/25.4)))
    if options.get('landscape'):size=landscape(size)
    if options.get('layout')=='standard':options={**options,'columns':1,'rows':1}
    columns=min(10,max(1,int(options.get('columns',4))));rows=int(options.get('rows',5));rows=min(12,max(1,rows));margin=25;cell_w=(size[0]-2*margin)/columns;cell_h=(size[1]-2*margin)/rows
    try:pdfmetrics.registerFont(TTFont('LFPrint',str(Path(reportlab.__file__).parent/'fonts/Vera.ttf')));font='LFPrint'
    except Exception:font='Helvetica'
    canvas=Canvas(str(out),pagesize=size);canvas.setTitle('LiquidFrame contact sheet')
    for index,i in enumerate(chosen):
        a=store.get_asset(i);preview=imaging.preview(i,1200);col=index%columns;row=(index//columns)%rows
        if index and index%(columns*rows)==0:canvas.showPage()
        x=margin+col*cell_w;y=size[1]-margin-(row+1)*cell_h
        canvas.drawImage(ImageReader(str(preview)),x+4,y+22,width=cell_w-8,height=cell_h-28,preserveAspectRatio=True,anchor='c',mask='auto');canvas.setFont(font,8);label=a.get(options.get('caption','title')) or a['name'];canvas.drawString(x+4,y+10,str(label)[:70])
    canvas.save();return uid
