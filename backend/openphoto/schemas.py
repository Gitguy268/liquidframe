"""Versioned request and recipe validation shared by API and persistence."""
from typing import Literal,Annotated
from pydantic import BaseModel,ConfigDict,Field,field_validator

class Strict(BaseModel): model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
class Stroke(Strict):
    points:list[tuple[Annotated[float,Field(ge=0,le=1)],Annotated[float,Field(ge=0,le=1)]]]=Field(max_length=20000)
    radius:float=Field(default=.025,ge=.001,le=.5)
    erase:bool=False
class Adjustments(Strict):
    advanced:dict=Field(default_factory=dict)
    disabled_groups:list[str]=Field(default_factory=list,max_length=30)
    @field_validator('advanced')
    @classmethod
    def valid_advanced(cls,value):
        from .adjustments import validate
        return validate(value)
    exposure:float=Field(default=0,ge=-5,le=5)
    contrast:float=Field(default=0,ge=-100,le=100)
    highlights:float=Field(default=0,ge=-100,le=100)
    shadows:float=Field(default=0,ge=-100,le=100)
    whites:float=Field(default=0,ge=-100,le=100)
    blacks:float=Field(default=0,ge=-100,le=100)
    temperature:float=Field(default=0,ge=-100,le=100)
    tint:float=Field(default=0,ge=-100,le=100)
    saturation:float=Field(default=0,ge=-100,le=100)
    vibrance:float=Field(default=0,ge=-100,le=100)
    sharpen:float=Field(default=0,ge=0,le=100)
    denoise:float=Field(default=0,ge=0,le=100)
    vignette:float=Field(default=0,ge=0,le=100)
    straighten:float=Field(default=0,ge=-45,le=45)
    rotate:Literal[0,90,180,270]=0
    flip_h:bool=False
    flip_v:bool=False
    crop:tuple[float,float,float,float]|None=None
    curve:list[tuple[float,float]]=Field(default_factory=list,max_length=32)
    hsl:dict[str,float]=Field(default_factory=dict)
    @field_validator('crop')
    @classmethod
    def valid_crop(cls,v):
        if v and (any(x<0 or x>1 for x in v) or v[2]<=0 or v[3]<=0 or v[0]+v[2]>1.00001 or v[1]+v[3]>1.00001):raise ValueError('Crop must be inside the image.')
        return v
    @field_validator('curve')
    @classmethod
    def valid_curve(cls,v):
        if any(x<0 or x>1 or y<0 or y>1 for x,y in v):raise ValueError('Curve coordinates must be between 0 and 1.')
        if len({x for x,_ in v})!=len(v):raise ValueError('Curve points must have unique input values.')
        return v
    @field_validator('hsl')
    @classmethod
    def valid_hsl(cls,v):
        if any(k not in ('hue','saturation','lightness') or abs(x)>(180 if k=='hue' else 100) for k,x in v.items()):raise ValueError('Invalid HSL control.')
        return v
class Raw(Strict):
    white_balance:Literal['camera','auto','custom']='camera'
    exposure:float=Field(default=0,ge=-5,le=5)
    temperature:float=Field(default=6500,ge=2000,le=12000)
    tint:float=Field(default=0,ge=-100,le=100)
    highlight_recovery:int=Field(default=0,ge=0,le=9)
    demosaic:Literal['AHD','LINEAR','VNG','PPG']='AHD'
class Operation(Strict):
    tool:Literal['background','cleanup','enhance']
    result:str=Field(pattern=r'^[a-f0-9]{32}\.tif$')
    adjustments:Adjustments=Field(default_factory=Adjustments)
    precision:str='AI processed in sRGB; model detail is not original sensor precision.'
class Recipe(Strict):
    schema_version:int=Field(default=1,ge=1,le=2)
    video:dict|None=None
    engine:dict|None=None
    frame:int=Field(default=0,ge=0,le=10000)
    adjustments:Adjustments=Field(default_factory=Adjustments)
    raw:Raw|None=None
    operations:list[Operation]=Field(default_factory=list,max_length=30)
class SaveRecipe(Strict):
    revision:int
    version:int
    recipe:Recipe
class Preview(Strict):
    revision:int
    recipe:Recipe
    size:int=Field(default=1200,ge=64,le=2048)
class Folder(Strict):
    path:str
    kind:Literal['library','export']='library'
class Name(Strict): name:str=Field(min_length=1,max_length=150)
class AssetIds(Strict): assets:list[str]=Field(max_length=100000)
class AI(Preview):
    tool:Literal['background','cleanup','enhance']
    strokes:list[Stroke]=Field(default_factory=list,max_length=500)
    feather:float=Field(default=2,ge=0,le=30)
    scale:Literal[1,2,4]=2
    strength:float=Field(default=.5,ge=0,le=1)
    background:str|None=Field(default=None,pattern=r'^#[a-fA-F0-9]{6}$')
class Options(Strict):
    format:str=Field(default='jpg',pattern=r'^[a-z0-9]{1,12}$')
    quality:int=Field(default=90,ge=1,le=100)
    bits:Literal[8,16]=8
    profile:Literal['srgb','source']='srgb'
    width:int|None=Field(default=None,ge=1,le=40000)
    height:int|None=Field(default=None,ge=1,le=40000)
    max_size:int|None=Field(default=None,ge=1,le=40000)
    strip_metadata:bool=False
    preserve_frames:bool=False
    background:str=Field(default='#ffffff',pattern=r'^#[a-fA-F0-9]{6}$')
class ExportAsset(Strict):
    id:str
    revision:int
    recipe:Recipe|None=None
class Export(Strict):
    assets:list[ExportAsset]=Field(min_length=1,max_length=100000)
    options:Options=Field(default_factory=Options)
    output_root:str|None=None
    replace:bool=False
    acknowledge_flatten:bool=False
class Analysis(Strict):
    kinds:list[Literal['semantic','people','duplicates']]=Field(default_factory=lambda:['duplicates'])
    root_id:str|None=None
class Downloads(Strict): models:list[Literal['background','cleanup','enhance','semantic','people','pets']]
class Favorite(Strict): favorite:bool
class Assign(Strict): person_id:str|None=None
class Preset(Name): recipe:Recipe
class Restore(Strict): backup_id:str
class Preferences(Strict):
    acceleration:Literal['cpu','auto']='cpu'
    theme:Literal['system','light','dark']='system'
    glass:bool=True
    cache_gb:int=Field(default=10,ge=1,le=100)

