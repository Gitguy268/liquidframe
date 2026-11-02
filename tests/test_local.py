import json,shutil,os,time
from pathlib import Path
import pytest,numpy as np,pyvips
from PIL import Image
from openphoto import store,imaging,library,exports,jobs
from .conftest import Context

def test_confined_blocks_traversal_and_symlink(tmp_path):
    root=tmp_path/'root';root.mkdir();outside=tmp_path/'outside';outside.mkdir()
    for path in ['../outside','/etc/passwd']:
        with pytest.raises(ValueError):store.confined(root,path,must_exist=False)
    (root/'escape').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError):store.confined(root,'escape/new.png',must_exist=False)

def test_incremental_revision_and_missing(asset,photo,ctx):
    root=asset['root_id'];library.scan({'root_id':root},ctx)
    assert store.get_asset(asset['id'])['revision']==1
    Image.new('RGB',(128,64),(11,22,33)).save(photo)
    with pytest.raises(ValueError):store.asset_path(asset)
    library.scan({'root_id':root},ctx);assert store.get_asset(asset['id'])['revision']==2
    photo.unlink();library.scan({'root_id':root},ctx);assert store.get_asset(asset['id'])['status']=='missing'

def test_overlap_does_not_duplicate(asset,photo,ctx):
    r=library.add_root(str(photo.parent.parent));library.scan({'root_id':r['id']},ctx)
    assert store.one('SELECT COUNT(*) n FROM assets')['n']==1

def test_recipe_version_conflict(asset):
    r=store.save_recipe(asset['id'],{'adjustments':{'exposure':.5}},0)
    assert r['version']==1
    with pytest.raises(ValueError):store.save_recipe(asset['id'],{},0)
    assert store.get_recipe(asset['id'])['recipe']['adjustments']['exposure']==.5

def test_16_bit_gradient_keeps_precision(tmp_path):
    values=np.tile(np.linspace(0,65535,2048,dtype=np.uint16),(8,1));rgb=np.repeat(values[:,:,None],3,axis=2)
    im=pyvips.Image.new_from_memory(rgb.tobytes(),2048,8,3,'ushort').copy(interpretation='rgb16')
    p=tmp_path/'gradient.tif';im.write_to_file(str(p))
    for fmt in ['png','tif']:
        target=tmp_path/('out.'+fmt);imaging.encode(p,{'adjustments':{'exposure':.15}},{'format':fmt,'bits':16},target)
        decoded=pyvips.Image.new_from_file(str(target));assert decoded.format=='ushort'
        a=np.frombuffer(decoded.write_to_memory(),np.uint16);assert len(np.unique(a))>1000

def test_manual_controls_dimensions(photo):
    rgb,alpha,meta=imaging.render(photo,{'adjustments':{'exposure':.4,'shadows':20,'highlights':-10,'temperature':20,'vibrance':10,'denoise':10,'sharpen':20,'vignette':10,'rotate':90,'crop':[0,0,.5,1],'curve':[[0,0],[.5,.4],[1,1]]}})
    assert (rgb.width,rgb.height)==(64,48);assert rgb.format=='float';assert rgb.avg()>0

def test_hsl(photo):
    im,_,_=imaging.render(photo,{'adjustments':{'hsl':{'hue':20,'saturation':10,'lightness':5}}})
    assert im.avg()>0

def test_transparency_and_metadata(tmp_path):
    p=tmp_path/'alpha.png';Image.new('RGBA',(32,32),(200,80,40,120)).save(p)
    out=tmp_path/'out.png';imaging.encode(p,{}, {'format':'png','bits':16},out)
    im=pyvips.Image.new_from_file(str(out));assert im.bands==4;assert im.format=='ushort'
    assert abs(im[3].avg()/65535-120/255)<.01

def test_opaque_export_composites_alpha(tmp_path):
    p=tmp_path/'alpha.png';Image.new('RGBA',(20,20),(10,20,30,0)).save(p)
    out=tmp_path/'out.jpg';imaging.encode(p,{}, {'format':'jpg','background':'#ffffff'},out)
    assert pyvips.Image.new_from_file(str(out)).avg()>250

@pytest.mark.parametrize('fmt',['jpg','png','webp','avif','tif','bmp','gif','ico'])
def test_format_roundtrip(photo,tmp_path,fmt):
    if not any(f['format']==fmt and f['write'] for f in imaging.formats()):pytest.skip('Codec not installed')
    target=tmp_path/('converted.'+fmt);imaging.encode(photo,{}, {'format':fmt},target);imaging.verify_output(target,fmt)

def test_svg_external_resources_are_blocked(tmp_path):
    p=tmp_path/'bad.svg';p.write_text('<svg xmlns="http://www.w3.org/2000/svg"><image href="https://example.com/track"/></svg>')
    with pytest.raises(ValueError):imaging.load(p)

def test_export_copy_and_replace_restore(asset,photo,tmp_path,ctx):
    original=store.digest(photo);target=tmp_path/'out';target.mkdir();root=library.add_root(str(target),'export')
    result=exports.export({'assets':[{'id':asset['id'],'revision':1,'recipe':{'adjustments':{'exposure':1}}}],'options':{'format':'png'},'output_root':root['id']},ctx)
    assert len(result['files'])==1;assert store.digest(photo)==original
    result=exports.export({'assets':[{'id':asset['id'],'revision':1,'recipe':{'adjustments':{'exposure':1}}}],'options':{'format':'png'},'replace':True},ctx)
    assert store.digest(photo)!=original
    b=result['files'][0]['backup_id'];assert b
    exports.restore({'backup_id':b},ctx);assert store.digest(photo)==original

def test_failed_backup_never_replaces(asset,photo,ctx,monkeypatch):
    h=store.digest(photo)
    def fail(*args):raise OSError('Backup drive unavailable')
    monkeypatch.setattr(exports,'atomic_copy',fail)
    with pytest.raises(ValueError):exports.export({'assets':[{'id':asset['id'],'revision':1,'recipe':{'adjustments':{'exposure':1}}}],'options':{'format':'png'},'replace':True},ctx)
    assert store.digest(photo)==h

def test_source_change_refuses_overwrite(asset,photo,ctx):
    Image.new('RGB',(100,100),'red').save(photo);h=store.digest(photo)
    with pytest.raises(ValueError):exports.export({'assets':[{'id':asset['id'],'revision':1}],'options':{'format':'png'},'replace':True},ctx)
    assert store.digest(photo)==h

def test_masks_align_and_erase():
    strokes=[{'points':[[.25,.5],[.75,.5]],'radius':.05}]
    a=imaging.paint_mask(strokes,200,100);b=imaging.paint_mask(strokes,400,200)
    assert a[50,100]==1 and a[0,0]==0 and b[100,200]==1
    erased=imaging.paint_mask([*strokes,{'points':[[.5,.5]],'radius':.1,'erase':True}],200,100)
    assert erased[50,100]==0

def test_duplicate_and_semantic_analysis_without_models(asset,photo,ctx):
    library.analyze({'kinds':['duplicates']},ctx)
    h=store.get_asset(asset['id']);assert h['sha256']==store.digest(photo);assert len(h['phash'])==16
    duplicate=photo.with_name('copy.png');shutil.copy2(photo,duplicate);library.scan({'root_id':asset['root_id']},ctx);library.analyze({'kinds':['duplicates']},ctx)
    groups=library.duplicates();assert groups[0]['kind']=='exact';assert len(groups[0]['assets'])==2

def test_job_resume_and_cancel():
    i=store.uid();store.execute('INSERT INTO jobs(id,kind,payload,state,created) VALUES(?,?,?,?,?)',(i,'scan','{}','cancelled',store.now()))
    with pytest.raises(jobs.Cancelled):jobs.Context(i).check()

def test_api_session_csrf_and_filters(asset):
    from fastapi.testclient import TestClient
    from openphoto.api import app
    with TestClient(app) as client:
        assert client.get('/api/v1/status').status_code==401
        client.get('/')
        assert client.get('/api/v1/status').status_code==200
        assert client.get('http://testserver:4321/api/v1/status').status_code==401
        client.get('http://testserver:4321/')
        assert client.get('http://testserver:4321/api/v1/status').status_code==200
        assert 'openphoto_session_80' in client.cookies and 'openphoto_session_4321' in client.cookies
        assert client.post('/api/v1/albums',json={'name':'Summer'}).status_code==403
        headers={'X-Openphoto':'1'}
        assert client.post('/api/v1/albums',json={'name':'Summer'},headers=headers).status_code==200
        assert client.get('/api/v1/assets?q=summer').json()['total']==1
        assert client.get('/api/v1/status',headers={'Origin':'https://evil.example'}).status_code==403
        assert client.get('/api/v1/status',headers={'Host':'evil.example'}).status_code==403
        bad=client.put('/api/v1/assets/'+asset['id']+'/recipe',headers=headers,json={'version':0,'revision':1,'recipe':{'adjustments':{'crop':[0,0,2,2]}}})
        assert bad.status_code==422

def test_100000_catalog_pagination(tmp_path):
    import sqlite3
    root=library.add_root(str(tmp_path))
    start=time.perf_counter()
    with store.db() as c:
        c.executemany('INSERT INTO assets(id,root_id,canonical_path,name,captured,status) VALUES(?,?,?,?,?,?)',((f'{i:032x}',root['id'],f'/virtual/{i}',f'photo-{i}.jpg','2026-10-14T12:00:00','ready') for i in range(100000)))
    rows=store.rows('SELECT id,name FROM assets ORDER BY captured DESC,id LIMIT 120 OFFSET 99000')
    assert len(rows)==120;assert store.one('SELECT COUNT(*) n FROM assets')['n']==100000
    from openphoto.api import assets as list_assets
    page=list_assets(offset=99000,limit=120)
    assert len(page['assets'])==120 and page['total']==100000
    assert len(json.dumps(page))<200000
    assert time.perf_counter()-start<30

def test_exif_orientation_normalized(tmp_path):
    p=tmp_path/'portrait.jpg';exif=Image.Exif();exif[274]=6
    Image.new('RGB',(80,40),(100,50,25)).save(p,exif=exif)
    assert imaging.metadata(p)[:2]==(40,80)
    out=tmp_path/'oriented.png';imaging.encode(p,{}, {'format':'png'},out)
    im=Image.open(out);assert im.size==(40,80);assert im.getexif().get(274,1)==1

def test_selected_animation_frame(tmp_path):
    p=tmp_path/'two.gif';Image.new('RGB',(32,32),'red').save(p,save_all=True,append_images=[Image.new('RGB',(32,32),'green')],duration=100,loop=0)
    a=imaging.array(imaging.render(p,{'frame':0})[0]);b=imaging.array(imaging.render(p,{'frame':1})[0])
    assert a[:,:,0].mean()>200 and b[:,:,1].mean()>100
    assert imaging.metadata(p)[3]['pages']==2

def test_hsl_keeps_16_bit_precision(tmp_path):
    values=np.tile(np.linspace(0,65535,2048,dtype=np.uint16),(8,1));rgb=np.stack([values,values//2,values//3],axis=2)
    im=pyvips.Image.new_from_memory(rgb.tobytes(),2048,8,3,'ushort').copy(interpretation='rgb16');p=tmp_path/'color.tif';im.write_to_file(str(p))
    out=tmp_path/'color.png';imaging.encode(p,{'adjustments':{'hsl':{'hue':10,'saturation':10,'lightness':5}}},{'format':'png','bits':16},out)
    decoded=pyvips.Image.new_from_file(str(out));assert decoded.format=='ushort'
    assert len(np.unique(np.frombuffer(decoded.write_to_memory(),np.uint16)))>2000

def test_image_cache_updates_after_file_replacement(tmp_path):
    p=tmp_path/'changing.png';Image.new('RGB',(30,30),'red').save(p)
    before=imaging.array(imaging.render(p)[0]);Image.new('RGB',(30,30),'green').save(p)
    after=imaging.array(imaging.render(p)[0]);assert not np.array_equal(before,after)

def test_large_photo_pipeline(tmp_path):
    p=tmp_path/'large.tif';im=(pyvips.Image.xyz(6000,4000)[0]%256).cast('uchar');im=im.bandjoin([im,im]).copy(interpretation='srgb');im.write_to_file(str(p),compression='lzw')
    rgb,_,_=imaging.render(p,{'adjustments':{'exposure':.2,'contrast':5}},preview=768)
    assert rgb.width==768 and rgb.avg()>0
    target=tmp_path/'large-out.tif';imaging.encode(p,{'adjustments':{'exposure':.2}},{'format':'tif','bits':16},target)
    assert imaging.metadata(target)[:3]==(6000,4000,16)

def test_original_comparison_ignores_saved_recipe(asset):
    from fastapi.testclient import TestClient
    from openphoto.api import app
    with TestClient(app) as c:
        c.get('/')
        original=c.get('/api/v1/assets/'+asset['id']+'/original').content
        assert c.get('/api/v1/assets').json()['assets'][0]['recipe_version']==0
        store.save_recipe(asset['id'],{'adjustments':{'exposure':1}},0)
        assert c.get('/api/v1/assets').json()['assets'][0]['recipe_version']==1
        assert c.get('/api/v1/assets/'+asset['id']+'/original').content==original
        assert c.get('/api/v1/assets/'+asset['id']+'/thumbnail').content!=original

def test_replace_refreshes_dimensions_and_bits(asset,photo,ctx):
    exports.export({'assets':[{'id':asset['id'],'revision':1,'recipe':{'adjustments':{'crop':[0,0,.5,1]}}}],'options':{'format':'png','bits':16},'replace':True},ctx)
    updated=store.get_asset(asset['id']);assert (updated['width'],updated['height'],updated['bits'])==(48,64,16)

@pytest.mark.skipif(os.name=='nt' or not imaging.MAGICK,reason='POSIX native codec regression')
def test_native_codec_uses_posix_spawn(monkeypatch):
    import subprocess
    calls=[];original=subprocess.Popen._posix_spawn
    def spy(self,*args,**kwargs):calls.append(True);return original(self,*args,**kwargs)
    monkeypatch.setattr(subprocess.Popen,'_posix_spawn',spy)
    output=imaging.command(['-list','format'])
    assert b'PNG' in output and calls

def test_persistent_export_resumes_completed_items(asset,photo,tmp_path,ctx):
    target=tmp_path/'exports';target.mkdir();root=library.add_root(str(target),'export')
    ctx.id=store.uid();store.execute('INSERT INTO jobs(id,kind,payload,state,created) VALUES(?,?,?,?,?)',(ctx.id,'export','{}','running',store.now()))
    payload={'assets':[{'id':asset['id'],'revision':1}],'options':{'format':'png'},'output_root':root['id']}
    first=exports.export(payload,ctx);second=exports.export(payload,ctx)
    assert first['file_count']==second['file_count']==1
    assert len(list(target.glob('*.png')))==1

def test_source_icc_roundtrip_without_srgb_clipping(tmp_path):
    from PIL import ImageCms
    p=tmp_path/'profile.png';profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    Image.new('RGB',(32,32),(45,150,230)).save(p,icc_profile=profile)
    out=tmp_path/'source-profile.tif';imaging.encode(p,{}, {'format':'tif','bits':16,'profile':'source'},out)
    restored=pyvips.Image.new_from_file(str(out));assert restored.format=='ushort'
    assert restored.get_typeof('icc-profile-data')
    actual=imaging.array(imaging.load(out)[0]);assert np.max(np.abs(actual[0,0].astype(int)-[45,150,230]))<=2

def test_float_derivative_keeps_unbounded_linear_values(tmp_path):
    values=np.array([[[-.05,.5,1.2]]],np.float32)
    im=pyvips.Image.new_from_memory(values.tobytes(),1,1,3,'float').copy(interpretation='scrgb')
    p=tmp_path/'result.tif';im.write_to_file(str(p))
    actual,_,_=imaging.load(p);assert actual.format=='float';assert np.allclose(actual(0,0),values[0,0],atol=1e-6)


def test_watcher_snapshot_does_not_block_request_thread(monkeypatch):
    import threading
    started=threading.Event();release=threading.Event()
    def snapshot():
        started.set();release.wait(timeout=3)
    monkeypatch.setattr(library,'build_watch',snapshot)
    before=time.perf_counter()
    try:
        library.start_watch()
        assert time.perf_counter()-before<.5
        assert started.wait(timeout=2)
    finally:
        release.set();library.stop_watch()


@pytest.mark.skipif(not imaging.MAGICK,reason='Native codec validation')
def test_wrong_native_format_is_rejected(tmp_path):
    p=tmp_path/'wrong.bmp';Image.new('RGB',(32,32),'red').save(p,format='PNG')
    with pytest.raises(ValueError,match='different format'):imaging.verify_output(p,'bmp')
