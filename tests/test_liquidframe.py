"""Acceptance checks for the new catalog, privacy and media services."""
import json,time,sqlite3,shutil
import numpy as np,pytest
from PIL import Image,ImageDraw,ImageFont
from openphoto import store,catalog,workspaces,library,imaging,media,deliveries,jobs

def test_additive_migration_and_private_history(asset,ctx):
    before=store.one('SELECT COUNT(*) n FROM assets')['n'];store.init()
    assert store.one('SELECT COUNT(*) n FROM assets')['n']==before
    catalog.patch_assets([asset['id']],{'title':'A day outside','keywords':['sky','sky'],'rating':4})
    assert catalog.query({'q':'outside'})['total']==1
    catalog.history_action();assert store.get_asset(asset['id'])['title']==''
    catalog.history_action(True);assert store.get_asset(asset['id'])['rating']==4
    workspaces.setup_passcode('sample-passcode')
    assert store.setting('private_passcode').startswith('$argon2id$')
    catalog.patch_assets([asset['id']],{'hidden':1})
    assert catalog.query()['total']==0
    with pytest.raises(PermissionError):store.get_asset(asset['id'])
    with pytest.raises(PermissionError):catalog.history_action()
    with workspaces.using(workspaces.resolve(),True):
        assert catalog.query({'view':'hidden'})['total']==1
        catalog.history_action()
    assert catalog.query()['total']==1

def test_trash_suppression_and_undo(asset,ctx):
    catalog.remove([asset['id']]);assert catalog.query()['total']==0
    library.scan({'root_id':asset['root_id']},ctx)
    assert catalog.query()['total']==0
    with workspaces.using(workspaces.resolve(),True):
        assert catalog.query({'view':'trash'})['total']==1
        catalog.history_action();assert catalog.query()['total']==1
        catalog.remove([asset['id']]);store.execute('UPDATE assets SET deleted_at=?',(store.now()-31*86400,));catalog.expire()
        assert catalog.query({'view':'trash'})['total']==0
    library.scan({'root_id':asset['root_id']},ctx);assert catalog.query()['total']==0

def test_smart_album_snapshot_and_context(asset,tmp_path):
    catalog.patch_assets([asset['id']],{'rating':5,'keywords':['outdoors']})
    album=catalog.create_album({'name':'Best','kind':'smart','rules':{'match':'all','conditions':[{'field':'rating','operator':'greater','value':3},{'field':'keyword','operator':'contains','value':'outdoors'}]}})
    assert catalog.query({'album_id':album['id']})['total']==1
    selection=catalog.snapshot({});assert catalog.ids(selection)==[asset['id']]
    other=workspaces.LibraryContext('other',tmp_path/'other','Other')
    with workspaces.using(other):
        store.init();assert catalog.query()['total']==0
        store.set_setting('name','other')
    assert catalog.query()['total']==1 and store.setting('name') is None

def test_private_endpoints_and_expired_jobs(asset,monkeypatch):
    from fastapi.testclient import TestClient
    from openphoto.api import app
    workspaces.setup_passcode('private-test')
    catalog.patch_assets([asset['id']],{'hidden':1})
    headers={'X-Openphoto':'1'}
    with TestClient(app) as c:
        c.get('/')
        path='/api/v1/assets/'+asset['id']
        for endpoint in [path,path+'/thumbnail',path+'/original','/api/v1/media/'+asset['id']+'/source']:
            response=c.get(endpoint);assert response.status_code==403;assert response.headers['cache-control']=='no-store'
        assert c.post('/api/v1/query',json={'view':'hidden'},headers=headers).status_code==403
        assert c.post('/api/v1/private/unlock',json={'passcode':'private-test'},headers=headers).status_code==200
        assert c.get(path).status_code==200
        token=c.cookies.get('liquidframe_private_80');workspaces.SESSIONS[token]['until']=time.time()-1
        assert c.get(path).status_code==403

def test_advanced_mask_float_and_group_disable(tmp_path):
    rng=np.random.default_rng(3);pixels=rng.random((64,96,3),dtype=np.float32)*.5
    im=imaging.from_array(pixels,linear=True)
    stroke={'mode':'blur','points':[[.5,.5]],'radius':.08,'feather':0}
    out,_=imaging.manual(im,None,{'advanced':{'retouch':[stroke]}})
    actual=np.frombuffer(out.write_to_memory(),np.float32).reshape(pixels.shape)
    np.testing.assert_allclose(actual[:10],pixels[:10],atol=1e-6)
    assert np.abs(actual[32,48]-pixels[32,48]).sum()>.01
    disabled,_=imaging.manual(im,None,{'advanced':{'brightness':40},'disabled_groups':['Light']})
    np.testing.assert_allclose(np.frombuffer(disabled.write_to_memory(),np.float32).reshape(pixels.shape),pixels,atol=1e-6)
    transformed,_=imaging.manual(im,None,{'advanced':{'curves':{'red':[[0,0],[.5,.6],[1,1]]},'levels':{'rgb':{'gamma':1.2}}}})
    assert transformed.format=='float' and transformed.avg()>im.avg()

@pytest.mark.skipif(not media.executable('ffmpeg') or not media.executable('ffprobe'),reason='Local video tools absent')
def test_real_video_trim_speed_audio_and_print(asset,tmp_path,ctx):
    source=tmp_path/'test.mp4';output=tmp_path/'edited.mp4'
    media.run('ffmpeg',['-y','-v','error','-f','lavfi','-i','testsrc2=size=96x64:rate=12:duration=3','-f','lavfi','-i','sine=frequency=440:sample_rate=44100:duration=3','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',source])
    before=store.digest(source)
    media.render_video(source,{'video':{'start':.5,'end':2.5,'speed':2},'adjustments':{'exposure':.2,'crop':[0,0,.5,1]}},{'max_size':96},output,ctx)
    w,h,_,m,_=media.metadata(output)
    assert (w,h)==(48,64) and abs(m['duration']-1)<.2 and m['audio']
    assert store.digest(source)==before
    pdf=deliveries.print_pdf({'ids':[asset['id']]},{'columns':2,'paper':'A4','caption':'title'})
    assert (store.data()/'results'/(pdf+'.pdf')).read_bytes().startswith(b'%PDF')
    root=library.add_root(str(tmp_path));library.scan({'root_id':root['id']},ctx)
    vid=store.one("SELECT id FROM assets WHERE name='test.mp4'")['id']
    catalog.stack({'ids':[asset['id'],vid]},'live',asset['id'])
    result=media.live_effect({'asset_id':asset['id'],'effect':'long_exposure'},ctx)
    developed=store.data()/'results'/result['result']
    assert imaging.metadata(developed)[2]==16 and store.setting('result-owner-'+developed.name)==asset['id']

@pytest.mark.skipif(not media.executable('tesseract'),reason='Tesseract absent')
def test_real_ocr(tmp_path,ctx):
    from openphoto.intelligence import ocr
    p=tmp_path/'text';p.mkdir();image=Image.new('RGB',(1000,180),'white');draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',70) if __import__('sys').platform=='darwin' else ImageFont.load_default(size=70)
    draw.text((30,40),'LiquidFrame 2026',fill='black',font=font);image.save(p/'sample.png')
    r=library.add_root(str(p));library.scan({'root_id':r['id']},ctx);a=store.get_asset(store.one('SELECT id FROM assets')['id'])
    result=ocr(a);assert '2026' in json.dumps(result)
    assert catalog.query({'q':'2026'})['total']==1

def test_album_history_and_selection_revision(asset,tmp_path,ctx):
    album=catalog.create_album({'name':'Summer'})
    catalog.album_items(album['id'],{'ids':[asset['id']]})
    assert catalog.query({'album_id':album['id']})['total']==1
    catalog.album_mutation(album['id'],{'name':'Autumn'})
    catalog.history_action();assert store.one('SELECT name FROM albums')['name']=='Summer'
    catalog.album_mutation(album['id'],delete=True);assert not store.one('SELECT id FROM albums')
    catalog.history_action();assert catalog.query({'album_id':album['id']})['total']==1
    catalog.history_action(True);assert not store.one('SELECT id FROM albums')


def test_upload_managed_copy_and_private_result_owner(asset,photo):
    from fastapi.testclient import TestClient
    from openphoto.api import app
    headers={'X-Openphoto':'1'}
    with TestClient(app) as c:
        c.get('/')
        r=c.post('/api/v1/imports/upload',files=[('files',('sample.png',photo.read_bytes(),'image/png'))],headers=headers)
        assert r.status_code==200
        assert (store.data()/'managed/sample.png').is_file()
        # Derivatives cannot be attached to unrelated sources, even with a known filename.
        name='a'*32+'.tif';store.set_setting('result-owner-'+name,'another-source')
        bad=c.post('/api/v1/assets/'+asset['id']+'/preview',json={'revision':1,'recipe':{'operations':[{'tool':'cleanup','result':name,'adjustments':{}}]}},headers=headers)
        assert bad.status_code==403

@pytest.mark.skipif(not media.executable('ffmpeg'),reason='FFmpeg absent')
def test_real_slideshow_audio_original_export(asset,tmp_path,ctx):
    output=tmp_path/'exports';output.mkdir();root=library.add_root(str(output),'export')
    project=deliveries.create_project('A local memory','memory',{'ids':[asset['id']]})
    doc=project['document'];doc.update({'duration':1,'music':'gentle','motion':'none'})
    store.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(doc),project['id']))
    result=deliveries.project_export({'project_id':project['id'],'output_root':root['id']},ctx)
    video=__import__('pathlib').Path(result['files'][0]['path']);meta=media.metadata(video)[3]
    assert .8<=meta['duration']<=1.2 and meta['audio']
    result=deliveries.batch_export({'selection':{'ids':[asset['id']]},'output_root':root['id'],'mode':'original','options':{'xmp':True}},ctx)
    copied=__import__('pathlib').Path(result['files'][0]['path'])
    assert store.digest(copied)==store.digest(store.asset_path(asset)) and copied.with_suffix(copied.suffix+'.xmp').is_file()


def test_query_order_matches_viewer_and_grouping(asset,photo,ctx):
    from openphoto.api_more import neighbors
    for n in range(48):
        Image.new('RGB',(12,12),(n*4,80,100)).save(photo.parent/f'item-{n:02}.png')
    library.scan({'root_id':asset['root_id']},ctx)
    rows=catalog.query({'sort':'name'},0,100)['assets']
    for n,a in enumerate(rows):catalog.patch_assets([a['id']],{'title':f'Title {100-n:03}','rating':n%6})
    album=catalog.create_album({'name':'Ordered'})
    catalog.album_items(album['id'],[a['id'] for a in reversed(rows)])
    for query in [{'sort':'name'},{'sort':'rating'},{'sort':'custom','album_id':album['id']}]:
        result=catalog.query(query,0,100);ordered=[a['id'] for a in result['assets']]
        assert result['groups']==[]
        center=ordered[25];near=neighbors({'query':query,'asset_id':center})
        assert [a['id'] for a in near['assets']]==ordered[5:46]


def test_private_project_job_and_cancel(asset,monkeypatch):
    from fastapi.testclient import TestClient
    from openphoto.api import app
    workspaces.setup_passcode('private-jobs-test')
    project=deliveries.create_project('Private later','slideshow',{'ids':[asset['id']]})
    job=store.uid();now=store.now()
    store.execute("INSERT INTO jobs(id,kind,payload,state,message,created,updated) VALUES(?,?,?,'complete','Private filename',?,?)",(job,'project_export',json.dumps({'project_id':project['id']}),now,now))
    catalog.patch_assets([asset['id']],{'hidden':1})
    assert jobs.snapshot()[0]['message']=='Private task'
    with TestClient(app) as client:
        client.get('/')
        assert client.post(f'/api/v1/jobs/{job}/cancel',headers={'X-Openphoto':'1'}).status_code==403
        assert client.get('/api/v1/imports').json()==[]


def test_batch_controls_forwarded_and_revision_checked(asset,tmp_path,ctx):
    root=library.add_root(str(tmp_path),'export')
    payload={'selection':{'ids':[asset['id']]},'output_root':root['id'],'revisions':{asset['id']:asset['revision']},'options':{'format':'png','bits':16,'max_size':40,'profile':'srgb','metadata':False}}
    result=deliveries.batch_export(payload,ctx)
    saved=__import__('pathlib').Path(result['files'][0]['path'])
    w,h,bits,_,_=imaging.metadata(saved)
    assert max(w,h)==40 and bits==16
    store.execute('DELETE FROM export_items')
    store.execute('UPDATE assets SET revision=revision+1 WHERE id=?',(asset['id'],))
    with pytest.raises(ValueError,match='changed'):deliveries.batch_export(payload,ctx)


def test_advanced_controls_reject_unsafe_values_and_disable_base():
    from openphoto.api import Recipe
    from pydantic import ValidationError
    for invalid in [{'denoise_detail':{'radius':100000}}, {'curves':{'rgb':[[.5,0],[.5,1]]}}, {'retouch':[{'points':[[2,.5]]}]}]:
        with pytest.raises(ValidationError):Recipe.model_validate({'adjustments':{'advanced':invalid}})
    pixels=np.full((16,24,3),.2,np.float32);image=imaging.from_array(pixels,linear=True)
    out,_=imaging.manual(image,None,{'exposure':4,'sharpen':100,'vignette':100,'disabled_groups':['Light','Sharpen','Vignette']})
    np.testing.assert_allclose(np.frombuffer(out.write_to_memory(),np.float32).reshape(pixels.shape),pixels,atol=1e-6)


def test_hiding_item_revokes_captured_source_and_group(asset):
    from openphoto.api_more import manual_face
    workspaces.setup_passcode('private-boundary-test')
    face=manual_face(asset['id'],{'box':[.2,.2,.3,.3]})
    captured=store.get_asset(asset['id'])
    catalog.patch_assets([asset['id']],{'hidden':1})
    with pytest.raises(PermissionError):store.asset_path(captured)
    with pytest.raises(PermissionError):catalog.authorize_person(face['person_id'])
    with workspaces.using(workspaces.resolve(),True):
        assert store.asset_path(captured).is_file()
        catalog.authorize_person(face['person_id'])


def test_project_job_keeps_private_dependencies_after_project_removed(asset,monkeypatch):
    monkeypatch.setattr(jobs,'submit',lambda _:None)
    project=deliveries.create_project('Temporary project','slideshow',{'ids':[asset['id']]})
    job=jobs.create('project_export',{'project_id':project['id']})
    store.execute('DELETE FROM projects WHERE id=?',(project['id'],))
    workspaces.setup_passcode('project-dependency-test')
    catalog.patch_assets([asset['id']],{'hidden':1})
    assert jobs.is_private(store.one('SELECT * FROM jobs WHERE id=?',(job,)))


def test_disconnect_keeps_recipes_and_can_undo(asset):
    store.save_recipe(asset['id'],{'adjustments':{'exposure':.5}},0)
    before=store.get_recipe(asset['id'])
    catalog.detach_root(asset['root_id'])
    assert catalog.query()['total']==0 and store.get_recipe(asset['id'])==before
    with workspaces.using(workspaces.resolve(),True):
        with pytest.raises(ValueError,match='not connected'):store.asset_path(store.get_asset(asset['id']))
        catalog.history_action()
    assert store.asset_path(store.get_asset(asset['id'])).exists()
    assert store.get_recipe(asset['id'])==before
