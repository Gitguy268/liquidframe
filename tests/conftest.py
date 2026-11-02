import pytest
from openphoto import store,imaging
@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path/'data');store.init();imaging.FORMATS=None
    yield
@pytest.fixture
def photo(tmp_path):
    from PIL import Image
    p=tmp_path/'library';p.mkdir();source=p/'summer.png';Image.new('RGB',(96,64),(90,145,180)).save(source)
    return source
class Context:
    id='test'
    def check(self):pass
    def progress(self,*args):pass
@pytest.fixture
def ctx():return Context()
@pytest.fixture
def asset(photo,ctx):
    from openphoto import library
    r=library.add_root(str(photo.parent));library.scan({'root_id':r['id']},ctx)
    return store.get_asset(store.one('SELECT id FROM assets')['id'])
