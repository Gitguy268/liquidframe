import {useRef, useState, type PointerEvent} from 'react';
import {api, endpoint, type Asset} from './api';

type Box = [number, number, number, number];
export function FaceRegion({asset, onSave, onCancel}: {asset: Asset; onSave: () => void; onCancel: () => void}) {
  const [box, setBox] = useState<Box | null>(null);
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const start = useRef<[number, number] | null>(null);
  function point(event: PointerEvent<HTMLDivElement>): [number, number] {
    const rect = event.currentTarget.getBoundingClientRect();
    return [Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)), Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height))];
  }
  async function save() {
    if (!box || box[2] < .005 || box[3] < .005) return;
    setBusy(true); setError('');
    try {
      await api(`/assets/${asset.id}/faces/manual`, 'POST', {box, name: name.trim() || 'Unnamed person'});
      onSave();
    } catch (e) { setError((e as Error).message); setBusy(false); }
  }
  return <section className="face-region-editor" aria-label="Mark a face">
    <h3>Mark a face</h3><p className="small muted">Draw a rectangle around the face in the original photo, or enter its position below.</p>
    <div className="face-region-image" onPointerDown={event => {
      start.current = point(event); event.currentTarget.setPointerCapture(event.pointerId);
      setBox([start.current[0], start.current[1], 0, 0]);
    }} onPointerMove={event => {
      if (!start.current) return;
      const [x, y] = point(event), [sx, sy] = start.current;
      setBox([Math.min(x, sx), Math.min(y, sy), Math.abs(x - sx), Math.abs(y - sy)]);
    }} onPointerUp={() => {start.current = null;}} onPointerCancel={() => {start.current = null;}}>
      <img draggable={false} src={endpoint(`/assets/${asset.id}/original?size=1200`)} alt={`Mark a face in ${asset.name}`}/>
      {box && <span className="face-region-box" style={{left: box[0] * 100 + '%', top: box[1] * 100 + '%', width: box[2] * 100 + '%', height: box[3] * 100 + '%'}}/>}
    </div>
    <div className="face-coordinates">{['Left', 'Top', 'Width', 'Height'].map((label, index) => <label key={label}>{label} %<input aria-label={`Face ${label.toLowerCase()} percent`} type="number" min={0} max={100} step={.1} value={Number(((box?.[index] || 0) * 100).toFixed(1))} onChange={event => {
      const next: Box = [...(box || [0, 0, 0, 0])]; next[index] = Math.max(0, Math.min(100, Number(event.target.value))) / 100;
      next[2] = Math.min(next[2], 1 - next[0]); next[3] = Math.min(next[3], 1 - next[1]); setBox(next);
    }}/></label>)}</div>
    <label className="field">Name (optional)<input value={name} maxLength={150} onChange={event => setName(event.target.value)}/></label>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="panel-row"><button className="button secondary" onClick={onCancel}>Cancel</button><button className="button primary" disabled={busy || !box || box[2] < .005 || box[3] < .005} onClick={save}>Save face</button></div>
  </section>;
}
