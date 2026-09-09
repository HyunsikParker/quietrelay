import { ITEMS, ZONES, LIMITS, type Payload } from "../planner";

const title = (s: string) => s[0].toUpperCase() + s.slice(1);
function nextId(ids: string[], prefix: string) {
  const used = new Set(ids); let n = 1; while (used.has(`${prefix}-${n}`)) n++;
  return `${prefix}-${n}`;
}
type Props = { payload: Payload; tab: "Stock" | "Requests" | "Volunteers"; change: (fn: (p: Payload) => void) => void };

export function ResourceInputs({ payload, tab, change }: Props) {
  if (tab === "Stock") return <>
    {payload.stock.map((s, i) => <div className="input-record" key={s.lot_id}>
      <div className="record-label"><strong>{s.lot_id}{s.expires_on < payload.today && <small className="expired-lot">Expired · excluded</small>}</strong><button className="text-button" aria-label={`Remove lot ${i + 1}`} onClick={() => change(p => { p.stock.splice(i, 1); })}>Remove</button></div>
      <label>Item<select aria-label={`Lot ${i + 1} item`} value={s.item} onChange={e => change(p => { p.stock[i].item = e.target.value; })}>{ITEMS.map(item => <option key={item} value={item}>{title(item)}</option>)}</select></label>
      <div className="field-pair"><label>Units<input aria-label={`Lot ${i + 1} units`} type="number" min="1" max={LIMITS.units} value={Number.isNaN(s.units) ? "" : s.units} onChange={e => change(p => { p.stock[i].units = e.target.valueAsNumber; })} /></label><label>Expires<input aria-label={`Lot ${i + 1} expiry`} type="date" value={s.expires_on} onChange={e => change(p => { p.stock[i].expires_on = e.target.value; })} /></label></div>
    </div>)}
    {!payload.stock.length && <p>No stock recorded. Requests will need review until stock is added.</p>}
    <button className="secondary-button" disabled={payload.stock.length >= LIMITS.stock} onClick={() => change(p => { p.stock.push({ lot_id: nextId(p.stock.map(s => s.lot_id), "lot"), item: "rice", units: 1, expires_on: p.today }); })}>Add stock lot</button>
  </>;
  if (tab === "Volunteers") return <>
    <p className="field-help">Capacity is the number of requests one volunteer can take. Select every zone they cover.</p>
    {payload.volunteers.map((v, i) => <div className="input-record" key={v.volunteer_id}>
      <div className="record-label"><strong>{v.volunteer_id}</strong><button className="text-button" aria-label={`Remove volunteer ${i + 1}`} onClick={() => change(p => { p.volunteers.splice(i, 1); })}>Remove</button></div>
      <div className="zone-checks" role="group" aria-label={`Volunteer ${i + 1} zones`}>{ZONES.map(z => <label key={z}><input type="checkbox" checked={v.zones.includes(z)} onChange={e => change(p => { p.volunteers[i].zones = e.target.checked ? [...p.volunteers[i].zones, z] : p.volunteers[i].zones.filter(a => a !== z); })} />{title(z)}</label>)}</div>
      <label>Request capacity<input aria-label={`Volunteer ${i + 1} capacity`} type="number" min="1" max={LIMITS.capacity} value={Number.isNaN(v.capacity) ? "" : v.capacity} onChange={e => change(p => { p.volunteers[i].capacity = e.target.valueAsNumber; })} /></label>
    </div>)}
    {!payload.volunteers.length && <p>No volunteers recorded. Stock is not reserved for requests without a volunteer.</p>}
    <button className="secondary-button" disabled={payload.volunteers.length >= LIMITS.volunteers} onClick={() => change(p => { p.volunteers.push({ volunteer_id: nextId(p.volunteers.map(v => v.volunteer_id), "vol"), zones: ["north"], capacity: 1 }); })}>Add volunteer</button>
  </>;
  return <>
    {payload.requests.map((r, i) => <div className="input-record" key={r.request_id}>
      <div className="record-label"><strong>{r.request_id}</strong><button className="text-button" disabled={payload.requests.length === 1} aria-label={`Remove request ${i + 1}`} onClick={() => change(p => { p.requests.splice(i, 1); })}>Remove</button></div>
      <div className="field-pair"><label>Priority<select aria-label={`Request ${i + 1} priority`} value={r.urgency} onChange={e => change(p => { p.requests[i].urgency = Number(e.target.value); })}>{[5, 4, 3, 2, 1].map(n => <option key={n}>{n}</option>)}</select></label><label>Zone<select aria-label={`Request ${i + 1} zone`} value={r.zone} onChange={e => change(p => { p.requests[i].zone = e.target.value; })}>{ZONES.map(z => <option key={z} value={z}>{title(z)}</option>)}</select></label></div>
      {r.needs.map((n, j) => <div className="need-row" key={j}><label>Item<select aria-label={`Request ${i + 1} item ${j + 1}`} value={n.item} onChange={e => change(p => { p.requests[i].needs[j].item = e.target.value; })}>{ITEMS.filter(item => item === n.item || !r.needs.some(a => a.item === item)).map(item => <option key={item} value={item}>{title(item)}</option>)}</select></label><label>Units<input aria-label={`Request ${i + 1} units ${j + 1}`} type="number" min="1" max={LIMITS.units} value={Number.isNaN(n.units) ? "" : n.units} onChange={e => change(p => { p.requests[i].needs[j].units = e.target.valueAsNumber; })} /></label><button className="text-button" disabled={r.needs.length === 1} aria-label={`Remove item ${j + 1} from request ${i + 1}`} onClick={() => change(p => { p.requests[i].needs.splice(j, 1); })}>Remove</button></div>)}
      <button className="text-button" disabled={r.needs.length === ITEMS.length} onClick={() => change(p => { p.requests[i].needs.push({ item: ITEMS.find(item => !p.requests[i].needs.some(n => n.item === item))!, units: 1 }); })}>Add needed item</button>
    </div>)}
    <button className="secondary-button" disabled={payload.requests.length >= LIMITS.requests} onClick={() => change(p => { p.requests.push({ request_id: nextId(p.requests.map(r => r.request_id), "req"), zone: "north", urgency: 3, needs: [{ item: "rice", units: 1 }] }); })}>Add request</button>
  </>;
}
