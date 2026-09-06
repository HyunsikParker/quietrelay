import { ArrowRight, Check, ChevronDown, LoaderCircle, RotateCcw } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { Brand } from "./components/Brand";
import { runLocalPlan, type AuthoritativePlan } from "./api";
import { resolveExecutionMode } from "./replay";
import { reviewText } from "./review";
import { initialPayload, previewPlan, selectedPreview, validateInput, validateResult, type Payload } from "./planner";

const title = (s: string) => s[0].toUpperCase() + s.slice(1);
const zones = ["north", "east", "south"];
type InputTab = "Stock" | "Requests" | "Volunteers";

export function App() {
  const live = useMemo(() => resolveExecutionMode(window.location) === "live", []);
  const [payload, setPayload] = useState<Payload>(initialPayload);
  const [inputTab, setInputTab] = useState<InputTab>("Stock");
  const [result, setResult] = useState<AuthoritativePlan | null>(() => previewPlan(initialPayload(), false));
  const [resultKind, setResultKind] = useState("Control plan");
  const [selected, setSelected] = useState("req-4");
  const [zone, setZone] = useState("all");
  const [busy, setBusy] = useState(false);
  const running = useRef(false);
  const resultHeading = useRef<HTMLHeadingElement>(null);
  const [status, setStatus] = useState("Change a quantity, then replan to see what changes.");
  const [error, setError] = useState(false);
  const [decisions, setDecisions] = useState<Record<string, "approved" | "held">>({});
  const [activity, setActivity] = useState<string[]>([]);
  const [revision, setRevision] = useState(1);
  const baselineCount = useMemo(() => { try { return previewPlan(payload, false).plan.allocations.length; } catch { return null; } }, [payload]);
  const allocation = result?.plan.allocations.find(a => a.request_id === selected);
  const review = result?.plan.reviews.find(r => r.request_id === selected);
  const selectedRequest = payload.requests[Number(selected.split("-")[1]) - 1];
  const counts = result ? { ready: result.plan.allocations.length, review: result.plan.reviews.length } : null;

  function edit(change: (p: Payload) => void) {
    if (running.current) return;
    const next = structuredClone(payload); change(next); setPayload(next);
    setResult(null); setDecisions({}); setError(false);
    setStatus("Inputs changed. Replan before reviewing or approving.");
  }
  function reset() {
    if (running.current) return;
    const next = initialPayload(); setPayload(next); setResult(previewPlan(next, false));
    setResultKind("Control plan"); setDecisions({}); setSelected("req-4"); setZone("all"); setRevision(r => r + 1);
    setError(false); setStatus("Original sample restored. Earlier activity remains below.");
    setActivity(a => ["Sample restored; previous approvals cleared.", ...a].slice(0, 30));
  }
  async function run() {
    if (running.current) return;
    try { validateInput(payload); } catch (e) { setError(true); setStatus(e instanceof Error ? e.message : "Check your inputs."); return; }
    running.current = true; setBusy(true); setError(false);
    setStatus(live ? "Local agent is inspecting, selecting and validating. This can take up to 50 seconds." : "Calculating from the current inputs…");
    const submitted = structuredClone(payload);
    try {
      const start = performance.now();
      const next = validateResult(submitted, live ? await runLocalPlan(submitted) : selectedPreview(submitted));
      setResult(next); setZone("all"); setResultKind(live ? "Local agent result" : "Replanned allocations"); setDecisions({}); setRevision(r => r + 1);
      setSelected(next.plan.reviews[0]?.request_id ?? next.plan.allocations[0]?.request_id ?? "req-1");
      const elapsed = ((performance.now() - start) / 1000).toFixed(2);
      setStatus(`Replanned from current inputs in ${elapsed}s. Nothing dispatched.`);
      if (window.matchMedia("(max-width: 760px)").matches) requestAnimationFrame(() => resultHeading.current?.focus());
      setActivity(a => [`${live ? "Local agent" : "Browser preview"}: ${next.plan.allocations.length} ready, ${next.plan.reviews.length} to review. All earlier approvals cleared.`, ...a].slice(0, 30));
    } catch {
      setResult(null); setDecisions({}); setError(true);
      setStatus(live ? "Local agent could not verify this plan. Check that Ollama is running with the model in the README, then retry. No result was applied." : "This input could not be verified. Check the quantities and dates, then retry.");
    } finally { running.current = false; setBusy(false); }
  }
  function decide() {
    if (running.current || !result || decisions[selected]) return;
    const state = allocation ? "approved" : "held";
    setDecisions(d => ({ ...d, [selected]: state }));
    setActivity(a => [`Plan ${revision} · ${selected} ${state === "approved" ? "approved locally" : "marked for follow-up; no stock reserved"}.`, ...a].slice(0, 30));
  }
  function undo() {
    if (running.current || !decisions[selected]) return;
    setDecisions(d => { const next = { ...d }; delete next[selected]; return next; });
    setActivity(a => [`Plan ${revision} · ${selected} decision undone.`, ...a].slice(0, 30));
  }
  function saveReview() {
    if (running.current || !result || resultKind === "Control plan") return;
    try {
      const text = reviewText(payload, result, decisions, live ? "agent" : "preview");
      const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url; link.download = `quietrelay-review-plan-${revision}.txt`;
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setError(false); setStatus("Review download requested. The snapshot includes all requests, current inputs and local decisions.");
    } catch (e) { setError(true); setStatus(e instanceof Error ? e.message : "Review could not be saved."); }
  }

  return <div className="console">
    <a className="skip-link" href="#results">Skip to plan</a>
    <header className="masthead"><Brand /><div className="masthead-note">Community allocation desk</div><a href="https://github.com/HyunsikParker/quietrelay#run-the-integrated-console" target="_blank" rel="noreferrer">Run locally <ArrowRight size={15} /></a></header>
    <main>
      <div className="page-heading"><div><p className="eyebrow">Sample data · 22 Aug 2026</p><h1>Allocation plan</h1></div></div>
      <div className="execution-note"><strong>{live ? "Live local agent" : "Interactive preview · no live model"}</strong><span>{live ? "Strands + Ollama on this device." : "Calculates in your browser. Run locally to use the Strands agent."}</span></div>
      <div className="desk">
        <section className="input-panel" aria-labelledby="input-title">
          <div className="section-heading"><div><p className="eyebrow">Inputs</p><h2 id="input-title">Today’s resources</h2></div><button className="text-button" onClick={reset} disabled={busy} aria-label="Reset sample"><RotateCcw size={16} /> Reset</button></div>
          <p className="panel-description">Five sample requests. Changes clear earlier results and approvals.</p>
          <div className="input-tabs" role="group" aria-label="Scenario inputs">{(["Stock", "Requests", "Volunteers"] as const).map(t => <button type="button" id={`tab-${t}`} aria-controls={`panel-${t}`} aria-pressed={inputTab === t} key={t} onClick={() => setInputTab(t)}>{t}</button>)}</div>
          <div className="input-footer"><button className="primary-button" type="button" disabled={busy} onClick={run}>{busy ? <LoaderCircle className="spin" size={18} /> : null}{busy ? "Verifying plan…" : live ? "Run local agent" : "Replan this sample"}{!busy && <ArrowRight size={18} />}</button><p>Exact items only. Expired stock is excluded.</p></div>
          <fieldset disabled={busy} className="input-fields" id={`panel-${inputTab}`} aria-labelledby={`tab-${inputTab}`}>
            {inputTab === "Stock" && payload.stock.map((s, i) => <div className="input-record" key={s.lot_id}><div className="record-label"><strong>{title(s.item)}</strong><span>lot-{i + 1}</span></div><div className="field-pair"><label>Units<input aria-label={`${title(s.item)} stock units`} type="number" min="1" max="100" value={Number.isNaN(s.units) ? "" : s.units} onChange={e => edit(p => { p.stock[i].units = e.target.valueAsNumber; })} /></label><label>Expires<input aria-label={`${title(s.item)} expiry`} type="date" value={s.expires_on} onChange={e => edit(p => { p.stock[i].expires_on = e.target.value; })} /></label></div></div>)}
            {inputTab === "Requests" && payload.requests.map((r, i) => <div className="input-record" key={r.request_id}><div className="record-label"><strong>req-{i + 1}</strong><span>{title(r.needs[0].item)}</span></div><div className="field-triple"><label>Units<input aria-label={`Request ${i + 1} units`} type="number" min="1" max="100" value={Number.isNaN(r.needs[0].units) ? "" : r.needs[0].units} onChange={e => edit(p => { p.requests[i].needs[0].units = e.target.valueAsNumber; })} /></label><label>Priority<select aria-label={`Request ${i + 1} priority`} value={r.urgency} onChange={e => edit(p => { p.requests[i].urgency = Number(e.target.value); })}>{[5, 4, 3, 2, 1].map(n => <option key={n}>{n}</option>)}</select></label><label>Zone<select aria-label={`Request ${i + 1} zone`} value={r.zone} onChange={e => edit(p => { p.requests[i].zone = e.target.value; })}>{zones.map(z => <option key={z} value={z}>{title(z)}</option>)}</select></label></div></div>)}
            {inputTab === "Volunteers" && <><p className="field-help">Capacity is the number of requests one volunteer can take.</p>{payload.volunteers.map((v, i) => <div className="input-record" key={v.volunteer_id}><div className="record-label"><strong>vol-{i + 1}</strong><span>{v.zones.map(title).join(" + ")}</span></div><label>Request capacity<input aria-label={`Volunteer ${i + 1} capacity`} type="number" min="1" max="10" value={Number.isNaN(v.capacity) ? "" : v.capacity} onChange={e => edit(p => { p.volunteers[i].capacity = e.target.valueAsNumber; })} /></label></div>)}</>}
          </fieldset>

        </section>
        <section className="result-panel" id="results" aria-labelledby="result-title" aria-busy={busy}>
          <div className="section-heading"><div><p className="eyebrow">Plan {revision}</p><h2 id="result-title" ref={resultHeading} tabIndex={-1}>{result ? resultKind : "Ready to replan"}</h2></div><label className="zone-filter">Zone <select aria-label="Zone view" value={zone} onChange={e => { const next = e.target.value; setZone(next); const index = payload.requests.findIndex(r => next === "all" || r.zone === next); setSelected(index >= 0 ? `req-${index + 1}` : ""); }}><option value="all">All</option>{zones.map(z => <option value={z} key={z}>{title(z)}</option>)}</select></label></div>
          <div className={`run-status ${error ? "run-status--error" : ""}`} role="status">{status}</div>
          {counts && <div className="plan-summary"><div><b>{counts.ready}</b><span>ready</span></div><div><b>{counts.review}</b><span>to review</span></div><p>{resultKind === "Control plan" ? "First-fit control" : `${baselineCount} ready in the first-fit control`}<br /><span>{Object.values(decisions).filter(d => d === "approved").length} approved locally</span></p></div>}
          {!result ? <div className="empty-plan"><span>↳</span><h3>Your inputs are ready for a fresh plan.</h3><p>Use {live ? "Run local agent" : "Replan this sample"} to calculate allocations and review their evidence.</p></div> : <>
            <div className="allocation-list" aria-label="Request allocations">{payload.requests.map((r, i) => {
              const id = `req-${i + 1}`, a = result.plan.allocations.find(a => a.request_id === id);
              if (zone !== "all" && r.zone !== zone) return null;
              return <button key={id} className={`allocation-row ${id === selected ? "allocation-row--selected" : ""}`} aria-pressed={id === selected} onClick={() => setSelected(id)}><span className="request-id">{id}<small>{title(r.zone)}</small></span><span className="request-need">{title(r.needs[0].item)} <small>{r.needs[0].units} {r.needs[0].units === 1 ? "unit" : "units"} · {a?.volunteer_id ?? "Unassigned"}</small></span><span className={`row-state ${a ? "row-state--ready" : "row-state--review"}`}>{decisions[id] ? title(decisions[id]) : a ? "Ready" : "Review"}</span><ChevronDown size={16} /></button>;
            })}{!payload.requests.some(r => zone === "all" || r.zone === zone) && <p className="field-help">No requests in this zone.</p>}</div>
            {(allocation || review) && <section className="evidence" aria-labelledby="evidence-title"><div className="evidence-heading"><p className="eyebrow">Review</p><h3 id="evidence-title">{selected} <span>{allocation ? "Allocation evidence" : "Needs a decision"}</span></h3></div><div className="evidence-body"><div>{allocation ? <><p>{allocation.items.map(i => `${i.units} ${i.item} from ${i.lot_id}`).join("; ")}.</p><p>{allocation.volunteer_id} covers {title(selectedRequest.zone)}. Stock and capacity are included in this plan.</p></> : <><p className="review-reason">{review?.reason === "inventory_shortage" ? "Not enough unexpired stock" : "No available volunteer capacity"}</p>{review?.evidence.map(e => <p key={e}>{e}</p>)}<p>Add the missing resource and replan, or mark this request for follow-up.</p></>}<p className="boundary-note">{allocation ? "Approval records a local decision. It does not dispatch a volunteer." : "Follow-up does not reserve stock or complete the request."}</p></div><div className="decision-actions">{decisions[selected] ? <><p className="decision-saved"><Check size={16} /> {decisions[selected] === "approved" ? "Approved locally" : "Marked for follow-up"}</p><button className="secondary-button" disabled={busy} onClick={undo}>Undo decision</button></> : <button className="secondary-button" disabled={busy} onClick={decide}>{allocation ? "Approve locally" : "Mark for follow-up"}</button>}</div></div></section>}
          </>}
          <div className="review-export"><button className="secondary-button" disabled={busy || !result || resultKind === "Control plan"} onClick={saveReview}>Save review</button><p>Save all requests and current decisions as a text file. Replan first. Unreviewed requests remain marked as pending.</p></div>
          <details className="activity"><summary>Activity <span>{activity.length} {activity.length === 1 ? "event" : "events"}</span></summary>{activity.length ? <ol>{activity.map((a, i) => <li key={`${activity.length - i}-${a}`}>{a}</li>)}</ol> : <p>No decisions recorded yet.</p>}</details>
        </section>
      </div>
      <footer className="page-footer"><span>Synthetic data only. No messages, deliveries or payments are sent.</span><span>Edits and approvals stay in this tab and reset on reload.</span></footer>
    </main>
  </div>;
}
