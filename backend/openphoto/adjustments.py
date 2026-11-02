"""Version-two float adjustments. Legacy recipes never enter this stage."""
import math
import cv2,numpy as np,pyvips

def validate(parameters):
    """Bound new recipe controls before they reach native processing kernels."""
    allowed={'brightness','brilliance','definition','white_balance_sample','white_balance_mode','curves','levels','selective_color','black_white','sharpen_detail','denoise_detail','vignette_detail','retouch','perspective'}
    if set(parameters)-allowed:raise ValueError('Unknown advanced adjustment.')
    def number(value,minimum,maximum):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not minimum<=value<=maximum:raise ValueError('An adjustment is outside its supported range.')
    def fields(value,ranges):
        if not isinstance(value,dict) or set(value)-set(ranges):raise ValueError('Invalid adjustment controls.')
        for key,item in value.items():number(item,*ranges[key])
    for key in ['brightness','brilliance','definition']:
        if key in parameters:number(parameters[key],0 if key=='definition' else -100,100)
    if 'white_balance_sample' in parameters:
        sample=parameters['white_balance_sample']
        if not isinstance(sample,list) or len(sample)!=3:raise ValueError('White balance needs three sampled channels.')
        for value in sample:number(value,0,1)
    if parameters.get('white_balance_mode','neutral') not in ['neutral','skin']:raise ValueError('Unknown white-balance sample mode.')
    curves=parameters.get('curves',{})
    if not isinstance(curves,dict) or set(curves)-{'rgb','red','green','blue'}:raise ValueError('Unknown curve channel.')
    for points in curves.values():
        if not isinstance(points,list) or len(points)>32:raise ValueError('Use at most 32 curve points per channel.')
        xs=[]
        for point in points:
            if not isinstance(point,(list,tuple)) or len(point)!=2:raise ValueError('A curve point needs two coordinates.')
            for value in point:number(value,0,1)
            xs.append(point[0])
        if len(set(xs))!=len(xs):raise ValueError('Curve inputs must be unique.')
    levels=parameters.get('levels',{})
    if not isinstance(levels,dict) or set(levels)-{'rgb','red','green','blue'}:raise ValueError('Unknown Levels channel.')
    for value in levels.values():
        fields(value,{'black':(0,1),'white':(0,1),'gamma':(.1,10),'out_black':(0,1),'out_white':(0,1)})
        if value.get('black',0)>=value.get('white',1):raise ValueError('Levels require black below white.')
    colors=parameters.get('selective_color',[])
    if not isinstance(colors,list) or len(colors)>24:raise ValueError('Use at most 24 selective-color ranges.')
    for color in colors:fields(color,{'center':(0,360),'range':(1,180),'hue':(-180,180),'saturation':(-100,100),'lightness':(-100,100)})
    for key,ranges in {'sharpen_detail':{'amount':(0,100),'edges':(0,100),'falloff':(.1,5)},'denoise_detail':{'luminance':(0,100),'color':(0,100),'detail':(0,100),'radius':(.1,4)},'vignette_detail':{'amount':(0,100),'radius':(.05,.7),'softness':(.01,.7)},'perspective':{'vertical':(-.4,.4),'horizontal':(-.4,.4)}}.items():
        if key in parameters:fields(parameters[key],ranges)
    if 'black_white' in parameters:
        bw=dict(parameters['black_white']);enabled=bw.pop('enabled',False)
        if not isinstance(enabled,bool):raise ValueError('Black and white enable must be boolean.')
        fields(bw,{'intensity':(0,1),'neutrals':(-100,100),'tone':(-100,100),'grain':(0,100)})
    strokes=parameters.get('retouch',[])
    if not isinstance(strokes,list) or len(strokes)>500:raise ValueError('Too many retouch strokes.')
    total=0
    for stroke in strokes:
        if not isinstance(stroke,dict) or set(stroke)-{'points','radius','erase','feather','mode','source'}:raise ValueError('Invalid retouch stroke.')
        if stroke.get('mode','blur') not in ['clone','red_eye','blur','pixelate']:raise ValueError('Unknown retouch mode.')
        number(stroke.get('radius',.025),.000001,.5);number(stroke.get('feather',2),0,30)
        points=stroke.get('points',[]);total+=len(points)
        if not points or total>100000:raise ValueError('Use between one and 100,000 retouch points.')
        for point in [*points,*([stroke['source']] if 'source' in stroke else [])]:
            if not isinstance(point,(list,tuple)) or len(point)!=2:raise ValueError('A brush point needs two coordinates.')
            for value in point:number(value,0,1)
    return parameters

def apply(rgb,alpha,p,base):
    from .imaging import clamp,curve,paint_mask
    if not p:return rgb,alpha
    sample=p.get('white_balance_sample')
    if sample and len(sample)==3:
        source=np.maximum(np.asarray(sample,dtype=float),.0001);target=np.array([.67,.44,.34]) if p.get('white_balance_mode')=='skin' else np.ones(3)*np.mean(source)
        gains=target/source;gains/=gains[1];rgb=rgb*np.clip(gains,.25,4).tolist()
    brightness=float(p.get('brightness',0))/100
    if brightness:rgb=rgb+brightness*.25
    l=rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722
    brilliance=float(p.get('brilliance',0))/100
    if brilliance:rgb=rgb+brilliance*.25*(1-clamp(l))**2-brilliance*.08*clamp(l)**4
    definition=float(p.get('definition',0))/100
    if definition:rgb=rgb+(rgb-rgb.gaussblur(max(2,min(rgb.width,rgb.height)/120)))*definition
    channels=[]
    for n,key in enumerate(['red','green','blue']):
        c=rgb[n];levels=(p.get('levels') or {}).get(key,(p.get('levels') or {}).get('rgb'))
        if levels:
            black=float(levels.get('black',0));white=float(levels.get('white',1));gamma=float(levels.get('gamma',1))
            if white<=black or not .1<=gamma<=10:raise ValueError('Levels need black < white and gamma 0.1–10.')
            c=clamp((c-black)/(white-black))**(1/gamma)
            c=c*(float(levels.get('out_white',1))-float(levels.get('out_black',0)))+float(levels.get('out_black',0))
        c=curve(c,(p.get('curves') or {}).get(key));channels.append(c)
    rgb=channels[0].bandjoin(channels[1:]).copy(interpretation='scrgb')
    if (p.get('curves') or {}).get('rgb'):rgb=curve(rgb,p['curves']['rgb'])
    for group in p.get('selective_color',[]):
        center=float(group.get('center',0))%360;radius=max(1,min(180,float(group.get('range',45))))
        c=clamp(rgb);r,g,b=c[0],c[1],c[2];mx=(r>g).ifthenelse(r,g);mx=(mx>b).ifthenelse(mx,b);mn=(r<g).ifthenelse(r,g);mn=(mn<b).ifthenelse(mn,b);delta=mx-mn
        hue=(mx==r).ifthenelse(((g-b)/(delta+1e-7))%6,(mx==g).ifthenelse((b-r)/(delta+1e-7)+2,(r-g)/(delta+1e-7)+4))*60
        distance=(hue-center).abs();distance=(distance>180).ifthenelse(360-distance,distance);weight=(1-clamp(distance/radius))*clamp(delta*5)
        angle=math.radians(float(group.get('hue',0)));cos=math.cos(angle);sin=math.sin(angle)
        matrix=[[.213+.787*cos-.213*sin,.715-.715*cos-.715*sin,.072-.072*cos+.928*sin],[.213-.213*cos+.143*sin,.715+.285*cos+.140*sin,.072-.072*cos-.283*sin],[.213-.213*cos-.787*sin,.715-.715*cos+.715*sin,.072+.928*cos+.072*sin]]
        shifted=rgb.recomb(matrix);lum=shifted[0]*.2126+shifted[1]*.7152+shifted[2]*.0722
        shifted=lum+(shifted-lum)*(1+float(group.get('saturation',0))/100)
        shifted+=float(group.get('lightness',0))/100*.25
        rgb=rgb*(1-weight)+shifted*weight
    bw=p.get('black_white',{})
    if bw.get('enabled'):
        intensity=float(bw.get('intensity',1));neutral=float(bw.get('neutrals',0))/100;tone=float(bw.get('tone',0))/100
        l=rgb[0]*(.2126+neutral*.12)+rgb[1]*(.7152-neutral*.12)+rgb[2]*.0722
        mono=(l-.18)*(1+tone*.5)+.18;mono=mono.bandjoin([mono,mono]);rgb=rgb*(1-intensity)+mono*intensity
        grain=float(bw.get('grain',0))/100
        if grain:rgb+=pyvips.Image.gaussnoise(rgb.width,rgb.height,mean=0,sigma=.025,seed=37)*grain
    denoise=p.get('denoise_detail',{})
    if denoise:
        lum=rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;blur=rgb.gaussblur(.5+float(denoise.get('radius',1)));lblur=lum.gaussblur(.5+float(denoise.get('radius',1)))
        color=float(denoise.get('color',0))/100;light=float(denoise.get('luminance',0))/100;detail=float(denoise.get('detail',50))/100
        rgb=lum+(rgb-lum)*(1-color)+(blur-lblur)*color+(lblur-lum)*light*(1-detail*.8)
    detail=p.get('sharpen_detail',{})
    if detail:
        amount=float(base.get('sharpen',detail.get('amount',0)))/100;radius=max(.1,float(detail.get('falloff',1)));edge=float(detail.get('edges',0))/100
        diff=rgb-rgb.gaussblur(radius);mask=clamp((diff[0].abs()+diff[1].abs()+diff[2].abs())*20-edge)
        rgb+=diff*amount*mask
    vig=p.get('vignette_detail',{})
    if vig:
        xy=pyvips.Image.xyz(rgb.width,rgb.height);d=((xy[0]/max(1,rgb.width-1)-.5)**2+(xy[1]/max(1,rgb.height-1)-.5)**2)**.5
        radius=max(.05,float(vig.get('radius',.35)));soft=max(.01,float(vig.get('softness',.3)))
        rgb*=1-clamp((d-radius)/soft)*float(base.get('vignette',vig.get('amount',0)))/100*.8
    for stroke in p.get('retouch',[]):
        mask=paint_mask([stroke],rgb.width,rgb.height,stroke.get('feather',2)).astype(np.float32)
        m=pyvips.Image.new_from_memory(mask.tobytes(),rgb.width,rgb.height,1,'float')
        kind=stroke.get('mode','blur')
        if kind=='clone':
            source=stroke.get('source',[.5,.5]);dest=stroke['points'][0];dx=(dest[0]-source[0])*rgb.width;dy=(dest[1]-source[1])*rgb.height
            replacement=rgb.affine([1,0,0,1],odx=dx,ody=dy,oarea=[0,0,rgb.width,rgb.height],extend='copy')
        elif kind=='pixelate':
            down=rgb.resize(.03);replacement=down.resize(rgb.width/down.width,vscale=rgb.height/down.height,kernel='nearest')
        elif kind=='red_eye':
            r,g,b=rgb[0],rgb[1],rgb[2];red=(r>g*1.3)&(r>b*1.3);replacement=red.ifthenelse((g+b)/2,r).bandjoin([g,b])
        else:replacement=rgb.gaussblur(max(2,min(rgb.width,rgb.height)*.02))
        rgb=rgb*(1-m)+replacement*m
    perspective=p.get('perspective',{})
    if perspective:
        w,h=rgb.width,rgb.height;v=max(-.4,min(.4,float(perspective.get('vertical',0))));u=max(-.4,min(.4,float(perspective.get('horizontal',0))))
        src=np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]])
        dst=np.float32([[w*(v+u),h*u],[w*(1-v+u),-h*u],[w*(1+v-u),h*(1+u)],[-w*(v+u),h*(1-u)]])
        inverse=np.linalg.inv(cv2.getPerspectiveTransform(src,dst));xy=pyvips.Image.xyz(w,h);x,y=xy[0],xy[1];z=x*inverse[2,0]+y*inverse[2,1]+inverse[2,2]
        coords=((x*inverse[0,0]+y*inverse[0,1]+inverse[0,2])/z).bandjoin((x*inverse[1,0]+y*inverse[1,1]+inverse[1,2])/z)
        rgb=rgb.mapim(coords,interpolate=pyvips.Interpolate.new('bicubic'),extend='black')
        if alpha is None:alpha=pyvips.Image.black(w,h).new_from_image(1).cast('float')
        alpha=alpha.mapim(coords,extend='black')
    return rgb.copy(interpretation='scrgb'),alpha

def auto_straighten(path):
    from . import imaging
    image=imaging.array(imaging.render(path,preview=1024)[0]);gray=cv2.cvtColor(image,cv2.COLOR_RGB2GRAY);lines=cv2.HoughLinesP(cv2.Canny(gray,50,150),1,np.pi/180,60,minLineLength=max(30,image.shape[1]//8),maxLineGap=20)
    angles=[]
    for line in lines if lines is not None else []:
        x1,y1,x2,y2=line[0];angle=math.degrees(math.atan2(y2-y1,x2-x1))
        if abs(angle)<15:angles.append(angle)
    return -float(np.median(angles)) if angles else 0

LOOKS={
 'Original':{},'Brilliant':{'contrast':10,'vibrance':20,'highlights':-8},'Warm':{'temperature':18,'saturation':6},'Cool':{'temperature':-18,'contrast':5},'Crisp':{'contrast':20,'sharpen':25},'Soft':{'contrast':-14,'highlights':-12,'shadows':12},'Mono':{'advanced':{'black_white':{'enabled':True,'intensity':1}}},'Silver':{'advanced':{'black_white':{'enabled':True,'intensity':1,'tone':20,'grain':12}}},'Nocturne':{'contrast':30,'blacks':-18,'saturation':-15},'Faded':{'contrast':-20,'blacks':15,'temperature':5}}
