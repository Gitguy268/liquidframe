import numpy as np,pyvips
from openphoto import store,imaging,models

def high_precision(asset):
    path=store.asset_path(asset)
    x=np.linspace(2000,60000,96*64,dtype=np.uint16).reshape(64,96)
    a=np.stack([x,x//2,x//3],axis=2)
    im=pyvips.Image.new_from_memory(a.tobytes(),96,64,3,'ushort').copy(interpretation='rgb16')
    im.set_type(pyvips.GValue.blob_type,'icc-profile-data',imaging.SRGB)
    im.write_to_file(str(path));return store.update_source(asset['id'])

def values(im):return np.frombuffer(im.cast('float').write_to_memory(),np.float32).reshape(im.height,im.width,im.bands).copy()

def test_cleanup_keeps_16_bit_values_outside_mask(asset,ctx,monkeypatch):
    a=high_precision(asset);source=imaging.render(store.asset_path(a))[0]
    strokes=[{'points':[[.5,.5]],'radius':.1}]
    monkeypatch.setattr(models,'cleanup',lambda pixels,strokes,ctx,feather:np.zeros_like(pixels))
    job=models.ai({'asset_id':a['id'],'revision':a['revision'],'tool':'cleanup','recipe':{},'strokes':strokes},ctx)
    result,_,_=imaging.load(store.DATA/'results'/job['operation']['result'])
    mask=imaging.paint_mask(strokes,source.width,source.height)>0
    actual=values(result)
    assert np.allclose(values(source)[~mask],actual[~mask],atol=1e-6)
    assert np.max(actual[mask])==0
    assert result.format=='float'

def test_background_preserves_original_rgb_and_alpha(asset,ctx,monkeypatch):
    a=high_precision(asset);source=imaging.render(store.asset_path(a))[0]
    monkeypatch.setattr(models,'cutout',lambda pixels,ctx,strokes,feather:np.full(pixels.shape[:2],.5,np.float32))
    job=models.ai({'asset_id':a['id'],'revision':a['revision'],'tool':'background','recipe':{}},ctx)
    result,alpha,_=imaging.load(store.DATA/'results'/job['operation']['result'])
    assert alpha is not None
    actual=values(result.bandjoin(alpha))
    assert np.allclose(values(source),actual[:,:,:3],atol=1e-6)
    assert abs(float(actual[:,:,3].mean())-.5)<1e-6
