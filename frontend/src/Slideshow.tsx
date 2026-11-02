import {useEffect, useRef, useState} from 'react';
import {endpoint, thumbnail, type Asset} from './api';
import {Icon} from './Icon';

export function Slideshow({items, document: project, onClose}: {items: Asset[]; document: any; onClose: () => void}) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [failed, setFailed] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const item = items[index];
  const seconds = Math.max(1, Math.min(60, project.duration || 4));
  function advance(direction: number) {
    setIndex(current => {
      const next = current + direction;
      if (next >= items.length) { if (project.loop) return 0; setPlaying(false); return current; }
      return Math.max(0, next);
    });
  }
  useEffect(() => {root.current?.focus();}, []);
  useEffect(() => {
    setFailed(false);
    if (!playing) return;
    const timer = setTimeout(() => advance(1), seconds * 1000);
    return () => clearTimeout(timer);
  }, [index, playing, seconds, project.loop]);
  useEffect(() => {
    if (!video.current) return;
    if (playing) video.current.play().catch(() => setPlaying(false)); else video.current.pause();
  }, [playing, index]);
  if (!item) return null;
  return <div className="slideshow-player" role="dialog" aria-modal="true" aria-label="Slideshow preview" ref={root} tabIndex={-1} onKeyDown={event => {
    if (event.key === 'Escape') onClose();
    if (event.key === 'ArrowRight') {event.preventDefault(); advance(1);}
    if (event.key === 'ArrowLeft') {event.preventDefault(); advance(-1);}
    if (event.key === ' ') {event.preventDefault(); setPlaying(value => !value);}
    if (event.key === 'Tab') {
      const buttons = root.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)');
      if (buttons?.length && event.shiftKey && (window.document.activeElement === buttons[0] || window.document.activeElement === root.current)) {event.preventDefault(); buttons[buttons.length - 1].focus();}
      else if (buttons?.length && !event.shiftKey && window.document.activeElement === buttons[buttons.length - 1]) {event.preventDefault(); buttons[0].focus();}
    }
  }}>
    <div key={item.id} className={`slideshow-image ${project.transition === 'fade' ? 'fade' : ''} ${project.motion === 'gentle' && playing ? 'motion' : ''}`} style={{animationDuration: project.transition === 'fade' ? '.6s' : '0s'}}>
      {item.media_kind === 'video' ? <video ref={video} src={endpoint(`/media/${item.id}/source`)} autoPlay muted playsInline onError={() => setFailed(true)} style={{objectFit: project.fit === 'fill' ? 'cover' : 'contain'}}/> : <img alt={item.title || item.name} src={project.look && project.look !== 'Original' ? endpoint(`/assets/${item.id}/look-preview?look=${encodeURIComponent(project.look)}`) : thumbnail(item.id,2048,String(item.recipe_version || item.revision))} style={{objectFit: project.fit === 'fill' ? 'cover' : 'contain', animationDuration: `${seconds}s`, animationPlayState: playing ? 'running' : 'paused'}}/>}
    </div>
    {failed && <p className="slideshow-notice">This video needs a compatible browser playback copy. It can still be rendered in the video export.</p>}
    <div className="slideshow-caption"><strong>{item.title || item.name}</strong><span>{index + 1} / {items.length}</span></div>
    <div className="slideshow-controls"><button aria-label="Previous slide" disabled={index === 0} onClick={() => advance(-1)}><Icon name="arrow-left"/></button><button onClick={() => setPlaying(value => !value)}>{playing ? 'Pause' : 'Play'}</button><button aria-label="Next slide" disabled={index === items.length - 1 && !project.loop} onClick={() => advance(1)}><Icon name="arrow-right"/></button><button onClick={() => {if (window.document.fullscreenElement) window.document.exitFullscreen(); else root.current?.requestFullscreen();}}>Fullscreen</button><button onClick={onClose}>Done</button></div>
    {project.music !== 'none' && <span className="slideshow-preview-note">Music is included in the rendered video export.</span>}
  </div>;
}
