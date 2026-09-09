import { ArrowRight, Check, ChevronDown, LoaderCircle, RotateCcw } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { Brand } from "./components/Brand";
import { ImportData } from "./components/ImportData";
import { ResourceInputs } from "./components/ResourceInputs";
import { runLocalPlan, type AuthoritativePlan } from "./api";
import { resolveExecutionMode } from "./replay";
import { reviewText } from "./review";
import { initialPayload, previewPlan, selectedPreview, validateInput, validateResult, type Payload } from "./planner";
import { MAX_WORKSPACE_BYTES, parseWorkspace, readSavedWorkspace, serializeWorkspace, writeSavedWorkspace, type Workspace } from "./workspace";

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
  const [snapshot, setSnapshot] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [saved, setSaved] = useState(() => {
    try { return { workspace: readSavedWorkspace(window.localStorage), unreadable: false }; }
    catch { return { workspace: null, unreadable: true }; }
  });
  const [unsaved, setUnsaved] = useState(false);
  const snapshotField = useRef<HTMLTextAreaElement>(null);
  const snapshotVersion = useRef(0);
  const baselineCount = useMemo(() => { try { return previewPlan(payload, false).plan.allocations.length; } catch { return null; } }, [payload]);
  const allocation = result?.plan.allocations.find(a => a.request_id === selected);
  const review = result?.plan.reviews.find(r => r.request_id === selected);
  const selectedRequest = payload.requests[Number(selected.split("-")[1]) - 1];
  const sourceLot = (id: string) => payload.stock[Number(id.split("-")[1]) - 1]?.lot_id ?? id;
  const sourceVolunteer = (id: string) => payload.volunteers[Number(id.split("-")[1]) - 1]?.volunteer_id ?? id;
  const counts = result ? { ready: result.plan.allocations.length, review: result.plan.reviews.length } : null;

  function edit(change: (p: Payload) => void) {
    if (running.current) return;
    clearSnapshot();
    const next = structuredClone(payload); change(next); setPayload(next);
    setResult(null); setDecisions({}); setError(false);
    setUnsaved(true);
    setStatus("Inputs changed. Replan before reviewing or approving.");
  }
  function reset() {
    if (running.current) return;
    clearSnapshot();
    const next = initialPayload(); setPayload(next); setResult(previewPlan(next, false));
    setResultKind("Control plan"); setDecisions({}); setSelected("req-4"); setZone("all"); setRevision(r => r + 1);
    setError(false); setStatus("Original sample restored. Earlier activity remains below.");
    setUnsaved(true);
    setActivity(a => ["Sample restored; previous approvals cleared.", ...a].slice(0, 30));
  }
  async function run() {
    if (running.current) return;
    clearSnapshot();
    try { validateInput(payload); } catch (e) { setError(true); setStatus(e instanceof Error ? e.message : "Check your inputs."); return; }
    running.current = true; setBusy(true); setError(false);
    setStatus(live ? "Local agent is inspecting, selecting and validating. This can take up to 50 seconds." : "Calculating from the current inputs…");
    const submitted = structuredClone(payload);
    try {
      const start = performance.now();
      const next = validateResult(submitted, live ? await runLocalPlan(submitted) : selectedPreview(submitted));
      setResult(next); setZone("all"); setResultKind(live ? "Local agent result" : "Replanned allocations"); setDecisions({}); setRevision(r => r + 1);
      setUnsaved(true);
      setSelected(next.plan.reviews[0]?.request_id ?? next.plan.allocations[0]?.request_id ?? "req-1");
      const elapsed = ((performance.now() - start) / 1000).toFixed(2);
      setStatus(`Replanned from current inputs in ${elapsed}s. Nothing dispatched.`);
      if (window.matchMedia("(max-width: 760px)").matches) requestAnimationFrame(() => resultHeading.current?.focus());
      setActivity(a => [`${live ? "Local agent" : "Browser preview"}: ${next.plan.allocations.length} ready, ${next.plan.reviews.length} to review. All earlier approvals cleared.`, ...a].slice(0, 30));
    } catch {
      setResult(null); setDecisions({}); setError(true);
      setUnsaved(true);
      setStatus(live ? "Local agent could not verify this plan. Check that Ollama is running with the model in the README, then retry. No result was applied." : "This input could not be verified. Check the quantities and dates, then retry.");
    } finally { running.current = false; setBusy(false); }
  }
  function decide() {
    if (running.current || !result || resultKind === "Control plan" || decisions[selected]) return;
    clearSnapshot();
    const state = allocation ? "approved" : "held";
    setDecisions(d => ({ ...d, [selected]: state }));
    setUnsaved(true);
    setActivity(a => [`Plan ${revision} · ${selected} ${state === "approved" ? "approved locally" : "marked for follow-up; no stock reserved"}.`, ...a].slice(0, 30));
  }
  function undo() {
    if (running.current || !decisions[selected]) return;
    clearSnapshot();
    setDecisions(d => { const next = { ...d }; delete next[selected]; return next; });
    setUnsaved(true);
    setActivity(a => [`Plan ${revision} · ${selected} decision undone.`, ...a].slice(0, 30));
  }
  function clearSnapshot() {
    snapshotVersion.current += 1;
    setSnapshot(null);
  }
  function saveReview() {
    if (running.current || !result || resultKind === "Control plan") return;
    try {
      const text = reviewText(payload, result, decisions, resultKind === "Saved review" ? "saved" : live ? "agent" : "preview");
      snapshotVersion.current += 1;
      setSnapshot(text);
      setError(false); setStatus("Review snapshot ready below. Copy it or download a text file. Nothing dispatched.");
      requestAnimationFrame(() => snapshotField.current?.focus());
    } catch (e) { setError(true); setStatus(e instanceof Error ? e.message : "Review could not be prepared."); }
  }
  async function copyReview() {
    if (running.current || !snapshot) return;
    const version = snapshotVersion.current;
    try {
      await navigator.clipboard.writeText(snapshot);
      if (version !== snapshotVersion.current) return;
      setError(false); setStatus("Review snapshot copied. Later edits are not included.");
    } catch {
      if (version !== snapshotVersion.current) return;
      snapshotField.current?.focus(); snapshotField.current?.select();
      setError(false); setStatus("Automatic copying is unavailable. The review text is selected; use your device’s Copy command.");
    }
  }
  function downloadReview() {
    if (running.current || !snapshot) return;
    try {
      const url = URL.createObjectURL(new Blob([snapshot], { type: "text/plain;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url; link.download = `quietrelay-review-plan-${revision}.txt`;
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setError(false); setStatus("Download requested. If no file appears, copy the review text below.");
    } catch { setError(false); setStatus("Download unavailable. Copy the review text below instead."); }
  }

  function loadData(next: Payload) {
    if (running.current) return;
    validateInput(next);
    clearSnapshot(); setPayload(next); setResult(null); setDecisions({}); setSelected("req-1"); setZone("all");
    setImporting(false); setUnsaved(true); setError(false);
    setStatus(`${next.requests.length} requests loaded. Replan before making decisions.`);
    setActivity(a => ["New data loaded; earlier plan and approvals cleared.", ...a].slice(0, 30));
  }
  function workspaceText() {
    return serializeWorkspace(payload, resultKind === "Control plan" ? null : result, resultKind === "Control plan" ? {} : decisions);
  }
  function saveWorkspace() {
    if (running.current) return;
    try {
      const text = workspaceText(); writeSavedWorkspace(window.localStorage, text);
      setSaved({ workspace: parseWorkspace(text), unreadable: false }); setUnsaved(false); setError(false);
      setStatus("Workspace saved on this device. Inputs and current review decisions can be restored after reopening.");
    } catch { setError(true); setStatus("Your work is still open, but could not be saved here. Check inputs or download a workspace file instead."); }
  }
  function applyWorkspace(workspace: Workspace) {
    clearSnapshot(); setPayload(workspace.payload); setResult(workspace.result); setDecisions(workspace.decisions);
    setResultKind("Saved review"); setSelected("req-1"); setZone("all"); setRevision(r => r + 1); setUnsaved(false); setError(false);
    setStatus(workspace.result ? "Saved workspace restored and its plan checked against the inputs. No new model run or dispatch." : "Saved inputs restored. Replan before reviewing or approving.");
    setActivity([workspace.result ? "Workspace restored; stored decisions checked against the stored plan." : "Saved inputs restored; no earlier plan or approvals."]);
  }
  function restoreWorkspace() {
    if (running.current) return;
    try {
      const current = readSavedWorkspace(window.localStorage);
      if (!current) throw new Error();
      setSaved({ workspace: current, unreadable: false }); applyWorkspace(current);
    } catch { setError(true); setStatus("Saved workspace could not be verified. Current work has not been replaced."); }
  }
  async function openWorkspace(file?: File) {
    if (!file || running.current) return;
    if (file.size > MAX_WORKSPACE_BYTES) { setError(true); setStatus("Workspace file is too large. Current work is unchanged."); return; }
    running.current = true; setBusy(true);
    try { applyWorkspace(parseWorkspace(await file.text())); setUnsaved(true); }
    catch { setError(true); setStatus("This workspace could not be verified. Current work has not been replaced."); }
    finally { running.current = false; setBusy(false); }
  }
  function downloadWorkspace() {
    if (running.current) return;
    try {
      const text = workspaceText();
      const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
      const link = document.createElement("a"); link.href = url; link.download = `quietrelay-workspace-${payload.today}.json`;
      document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      setError(false); setStatus("Workspace download requested. Open that file here to resume on another device. Check that the file was saved.");
    } catch { setError(true); setStatus("Workspace could not be prepared. Check inputs; current work is unchanged."); }
  }

  return <div className="console">
    <a className="skip-link" href="#results">Skip to plan</a>
    <header className="masthead"><Brand /><div className="masthead-note">Community allocation desk</div><nav aria-label="Project evidence"><a href={`${import.meta.env.BASE_URL}walkthrough/index.html`}>Watch local agent</a><a href="https://github.com/HyunsikParker/quietrelay#run-the-integrated-console" target="_blank" rel="noreferrer">Run locally <ArrowRight size={15} /></a></nav></header>
    <main>
      <div className="page-heading"><div><p className="eyebrow">Anonymous allocation workspace</p><h1>Plan, review, hand over.</h1><p>Match requests to usable stock and volunteer capacity. Keep the decisions with their evidence.</p></div></div>
      <div className="execution-note"><strong>{live ? "Local agent mode" : "Interactive preview · no live model"}</strong><span>{live ? "Strands + Ollama on this device." : "Calculates in your browser. Run locally to use the Strands agent."}</span></div>
      <section className="workspace-bar" aria-label="Workspace">
        <div><strong>{unsaved ? "Changes not saved" : saved.workspace ? "Saved workspace available" : "Start with the sample or bring your data"}</strong><p>{saved.workspace ? `Last saved here: ${new Date(saved.workspace.savedAt).toLocaleString()}.` : "Use anonymous IDs, items and zones. No contact details."}</p>{saved.unreadable && <p>Browser storage is unavailable or its saved file could not be read. You can still download a workspace.</p>}</div>
        <div className="workspace-actions"><button className="secondary-button" disabled={busy} onClick={() => setImporting(true)}>Import tables</button><button className="secondary-button" disabled={busy} onClick={saveWorkspace}>Save workspace</button>{saved.workspace && <button className="secondary-button" disabled={busy} onClick={restoreWorkspace}>Restore saved work</button>}<button className="text-button" disabled={busy} onClick={downloadWorkspace}>Download workspace</button><label className={`file-control ${busy ? "disabled" : ""}`}>Open workspace<input type="file" accept=".json,application/json" disabled={busy} onChange={e => { void openWorkspace(e.target.files?.[0]); e.target.value = ""; }} /></label></div>
      </section>
      <div className="desk">
        <section className="input-panel" aria-labelledby="input-title">
          <div className="section-heading"><div><p className="eyebrow">Inputs</p><h2 id="input-title">Today’s resources</h2></div><button className="text-button" onClick={reset} disabled={busy} aria-label="Reset sample"><RotateCcw size={16} /> Reset</button></div>
          <p className="panel-description">{payload.requests.length} requests · {payload.stock.length} stock lots · {payload.volunteers.length} volunteers. Changes clear earlier results and approvals.</p>
          <label className="planning-date">Planning date<input type="date" value={payload.today} disabled={busy} onChange={e => edit(p => { p.today = e.target.value; })} /></label>
          <div className="input-tabs" role="group" aria-label="Scenario inputs">{(["Stock", "Requests", "Volunteers"] as const).map(t => <button type="button" id={`tab-${t}`} aria-controls={`panel-${t}`} aria-pressed={inputTab === t} key={t} onClick={() => setInputTab(t)}>{t}</button>)}</div>
          <div className="input-footer"><button className="primary-button" type="button" disabled={busy} onClick={run}>{busy ? <LoaderCircle className="spin" size={18} /> : null}{busy ? "Verifying plan…" : live ? "Run local agent" : "Replan"}{!busy && <ArrowRight size={18} />}</button><p>Exact items only. Expired stock is excluded.</p></div>
          <fieldset disabled={busy} className="input-fields" id={`panel-${inputTab}`} aria-labelledby={`tab-${inputTab}`}>
            <ResourceInputs payload={payload} tab={inputTab} change={edit} />
          </fieldset>

        </section>
        <section className="result-panel" id="results" aria-labelledby="result-title" aria-busy={busy}>
          <div className="section-heading"><div><p className="eyebrow">Plan {revision}</p><h2 id="result-title" ref={resultHeading} tabIndex={-1}>{result ? resultKind : "Ready to replan"}</h2></div><label className="zone-filter">Zone <select aria-label="Zone view" value={zone} onChange={e => { const next = e.target.value; setZone(next); const index = payload.requests.findIndex(r => next === "all" || r.zone === next); setSelected(index >= 0 ? `req-${index + 1}` : ""); }}><option value="all">All</option>{zones.map(z => <option value={z} key={z}>{title(z)}</option>)}</select></label></div>
          <div className={`run-status ${error ? "run-status--error" : ""}`} role="status">{status}</div>
          {counts && <div className="plan-summary"><div><b>{counts.ready}</b><span>ready</span></div><div><b>{counts.review}</b><span>to review</span></div><p>{resultKind === "Control plan" ? "First-fit control" : `${baselineCount} ready in the first-fit control`}<br /><span>{Object.values(decisions).filter(d => d === "approved").length} approved locally</span></p></div>}
          {!result ? <div className="empty-plan"><span>↳</span><h3>Your inputs are ready for a fresh plan.</h3><p>Use {live ? "Run local agent" : "Replan"} to calculate allocations and review their evidence.</p></div> : <>
            <div className="allocation-list" aria-label="Request allocations">{payload.requests.map((r, i) => {
              const id = `req-${i + 1}`, a = result.plan.allocations.find(a => a.request_id === id);
              if (zone !== "all" && r.zone !== zone) return null;
              return <button key={id} className={`allocation-row ${id === selected ? "allocation-row--selected" : ""}`} aria-pressed={id === selected} onClick={() => setSelected(id)}><span className="request-id">{r.request_id}<small>{title(r.zone)} · {id}</small></span><span className="request-need">{r.needs.map(n => `${n.units} ${n.item}`).join(" + ")}<small>{a ? sourceVolunteer(a.volunteer_id) : "Unassigned"}</small></span><span className={`row-state ${a ? "row-state--ready" : "row-state--review"}`}>{decisions[id] ? title(decisions[id]) : a ? "Ready" : "Review"}</span><ChevronDown size={16} /></button>;
            })}{!payload.requests.some(r => zone === "all" || r.zone === zone) && <p className="field-help">No requests in this zone.</p>}</div>
            {(allocation || review) && <section className="evidence" aria-labelledby="evidence-title"><div className="evidence-heading"><p className="eyebrow">Review</p><h3 id="evidence-title">{selectedRequest.request_id} <span>{allocation ? "Allocation evidence" : "Needs a decision"}</span></h3></div><div className="evidence-body"><div>{allocation ? <><p>{allocation.items.map(i => `${i.units} ${i.item} from ${sourceLot(i.lot_id)}`).join("; ")}.</p><p>{sourceVolunteer(allocation.volunteer_id)} covers {title(selectedRequest.zone)}. Stock and capacity are included in this plan.</p></> : <><p className="review-reason">{review?.reason === "inventory_shortage" ? "Not enough unexpired stock" : "No available volunteer capacity"}</p>{review?.evidence.map(e => <p key={e}>{e}</p>)}<p>Add the missing resource and replan, or mark this request for follow-up.</p></>}<p className="boundary-note">{allocation ? "Approval records a local decision. It does not dispatch a volunteer." : "Follow-up does not reserve stock or complete the request."}</p></div><div className="decision-actions">{decisions[selected] ? <><p className="decision-saved"><Check size={16} /> {decisions[selected] === "approved" ? "Approved locally" : "Marked for follow-up"}</p><button className="secondary-button" disabled={busy} onClick={undo}>Undo decision</button></> : <button className="secondary-button" disabled={busy || resultKind === "Control plan"} onClick={decide}>{allocation ? "Approve locally" : "Mark for follow-up"}</button>}</div></div></section>}
          </>}
          <div className="review-export"><button className="secondary-button" disabled={busy || !result || resultKind === "Control plan"} onClick={saveReview}>Prepare handover</button><p>Open a snapshot of all requests and decisions, then copy or download it. Unreviewed requests remain pending.</p></div>
          {snapshot && <section className="review-snapshot" aria-labelledby="snapshot-title"><h3 id="snapshot-title">Review snapshot</h3><p>Current inputs and decisions. Changing either closes this snapshot.</p><textarea ref={snapshotField} aria-label="Review snapshot text" readOnly value={snapshot} rows={12} spellCheck={false} /><div className="snapshot-actions"><button className="secondary-button" onClick={copyReview}>Copy review</button><button className="secondary-button" onClick={downloadReview}>Download text</button><button className="text-button" onClick={clearSnapshot}>Close snapshot</button></div></section>}
          <details className="activity"><summary>Activity <span>{activity.length} {activity.length === 1 ? "event" : "events"}</span></summary>{activity.length ? <ol>{activity.map((a, i) => <li key={`${activity.length - i}-${a}`}>{a}</li>)}</ol> : <p>No decisions recorded yet.</p>}</details>
        </section>
      </div>
      <footer className="page-footer"><span>Sample data is synthetic. No messages, deliveries or payments are sent.</span><span>Save or download your workspace before closing. Saving uses this browser’s local storage.</span></footer>
    </main>
    {importing && <ImportData payload={payload} onImport={loadData} onClose={() => setImporting(false)} />}
  </div>;
}
