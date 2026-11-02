import { useEffect, useRef, type ReactNode } from 'react';
import {MultiPassRenderer} from './vendor/liquid-glass/GLUtils';
import * as shader from './vendor/liquid-glass/shaders';

/** Shared lifecycle manager; original multipass renderer and optical shaders are upstream MIT. */
class GlassRenderer {
 private instances=new Map<HTMLElement,{dispose:()=>void;draw:()=>void}>();
 attach(element:HTMLElement,canvas:HTMLCanvasElement,photo?:HTMLImageElement|null){
  let renderer:MultiPassRenderer|null=null;let texture:WebGLTexture|null=null;let raf=0;let disposed=false;
  try{
   renderer=new MultiPassRenderer(canvas,[
    {name:'bg',shader:{vertex:shader.vertex,fragment:shader.background}},
    {name:'v',shader:{vertex:shader.vertex,fragment:shader.verticalBlur},inputs:{u_prevPassTexture:'bg'}},
    {name:'h',shader:{vertex:shader.vertex,fragment:shader.horizontalBlur},inputs:{u_prevPassTexture:'v'}},
    {name:'glass',shader:{vertex:shader.vertex,fragment:shader.glass},inputs:{u_bg:'bg',u_blurredBg:'h'},outputToScreen:true}
   ]);
  }catch{return ()=>{};}
  const gl=canvas.getContext('webgl2')!;
  const draw=()=>{
   if(disposed||document.hidden||!renderer)return;
   const rect=element.getBoundingClientRect(),dpr=Math.min(devicePixelRatio,1.5,1200/Math.max(rect.width,rect.height));
   const w=Math.max(2,Math.round(rect.width*dpr)),h=Math.max(2,Math.round(rect.height*dpr));
   canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h);renderer.resize(w,h);
   const scratch=document.createElement('canvas');scratch.width=w;scratch.height=h;const ctx=scratch.getContext('2d')!;
   const dark=document.documentElement.dataset.theme==='dark';ctx.fillStyle=dark?'#242424':'#ededed';ctx.fillRect(0,0,w,h);
   if(photo?.complete&&photo.naturalWidth){
    const imgRect=photo.getBoundingClientRect();
    const scale=Math.min(imgRect.width/photo.naturalWidth,imgRect.height/photo.naturalHeight);
    const iw=photo.naturalWidth*scale,ih=photo.naturalHeight*scale;
    const x=imgRect.left+(imgRect.width-iw)/2-rect.left,y=imgRect.top+(imgRect.height-ih)/2-rect.top;
    ctx.drawImage(photo,x*dpr,y*dpr,iw*dpr,ih*dpr);
   }
   if(texture)gl.deleteTexture(texture);texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);
   gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
   gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
   gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,true);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,scratch);
   const weights=Array.from({length:33},(_,i)=>Math.exp(-(i*i)/(2*4*4)));const sum=weights[0]+2*weights.slice(1).reduce((a,b)=>a+b,0);
   renderer.setUniforms({u_resolution:[w,h],u_dpr:dpr,u_mouse:[w/2,h/2],u_mouseSpring:[w/2,h/2],u_shapeWidth:rect.width-2,u_shapeHeight:rect.height-2,u_shapeRadius:Math.min(24,rect.height/2),u_shapeRoundness:4,u_mergeRate:.00001,u_showShape1:0,u_bgType:11,u_bgTextureReady:1,u_bgTexture:texture,u_bgTextureRatio:w/h,u_blurWeights:weights.map(v=>v/sum),u_blurRadius:12,u_tint:dark?[.06,.06,.06,.5]:[.99,.99,.99,.5],u_refThickness:16,u_refDistance:.018,u_refFactor:1.35,u_refDispersion:.3,u_refFresnelRange:55,u_refFresnelFactor:.22,u_refFresnelHardness:.02,u_glareRange:40,u_glareConvergence:1,u_glareOppositeFactor:.6,u_glareFactor:.2,u_glareHardness:0,u_glareAngle:.8,u_blurEdge:1,STEP:9,u_shadowFactor:0,u_shadowExpand:0,u_shadowPosition:[0,0]});
   try{renderer.render();canvas.dataset.ready='true';}catch{canvas.dataset.ready='false';}
  };
  const schedule=()=>{cancelAnimationFrame(raf);raf=requestAnimationFrame(draw);};
  const observer=new ResizeObserver(schedule);observer.observe(element);
  const onLost=(e:Event)=>{e.preventDefault();canvas.dataset.ready='false';};canvas.addEventListener('webglcontextlost',onLost);
  window.addEventListener('resize',schedule);window.addEventListener('scroll',schedule,true);document.addEventListener('visibilitychange',schedule);photo?.addEventListener('load',schedule);
  const mutation=new MutationObserver(schedule);mutation.observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
  const dispose=()=>{disposed=true;cancelAnimationFrame(raf);observer.disconnect();mutation.disconnect();window.removeEventListener('resize',schedule);window.removeEventListener('scroll',schedule,true);document.removeEventListener('visibilitychange',schedule);photo?.removeEventListener('load',schedule);canvas.removeEventListener('webglcontextlost',onLost);if(texture)gl.deleteTexture(texture);renderer?.dispose();this.instances.delete(element);};
  this.instances.set(element,{dispose,draw:schedule});schedule();return dispose;
 }
 refresh(){this.instances.forEach(x=>x.draw());}
}
export const glassRenderer=new GlassRenderer();
export function GlassSurface({children,className='',enabled=true,photo}:{children:ReactNode;className?:string;enabled?:boolean;photo?:HTMLImageElement|null}){
 const ref=useRef<HTMLDivElement>(null),canvas=useRef<HTMLCanvasElement>(null);
 useEffect(()=>{
  if(!enabled||matchMedia('(prefers-reduced-transparency: reduce)').matches)return;
  if(ref.current&&canvas.current)return glassRenderer.attach(ref.current,canvas.current,photo);
 },[enabled,photo]);
 return <div ref={ref} className={`glass-surface ${enabled?'glass-enabled':''} ${className}`}><canvas ref={canvas} aria-hidden="true" className="glass-canvas"/><div className="glass-content">{children}</div></div>;
}
