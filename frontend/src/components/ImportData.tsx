import { useEffect, useRef, useState } from "react";
import { initialPayload, type Payload } from "../planner";
import { parseSheets, payloadSheets, type Sheets } from "../intake";

export function ImportData({ payload, onImport, onClose }: { payload: Payload; onImport: (p: Payload) => void; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [sheets, setSheets] = useState<Sheets>(() => { try { return payloadSheets(payload); } catch { return payloadSheets(initialPayload()); } });
  const [today, setToday] = useState(payload.today);
  const [tab, setTab] = useState<keyof Sheets>("requests");
  const [error, setError] = useState("");
  const [candidate, setCandidate] = useState<Payload | null>(null);
  const loading = useRef(false);
  const [reading, setReading] = useState(false);
  useEffect(() => { dialog.current?.showModal(); }, []);
  function change(kind: keyof Sheets, text: string) { setSheets(s => ({ ...s, [kind]: text })); setCandidate(null); setError(""); }
  async function readFile(file?: File) {
    if (!file || loading.current) return;
    if (file.size > 80_000) { setError("Use a CSV file smaller than 80 KB."); return; }
    const target = tab;
    loading.current = true; setReading(true);
    try { change(target, await file.text()); } catch { setError("The file could not be read. You can paste its rows instead."); }
    finally { loading.current = false; setReading(false); }
  }
  function check() {
    try { setCandidate(parseSheets(today, sheets)); setError(""); } catch (e) { setCandidate(null); setError(e instanceof Error ? e.message : "Check the three tables."); }
  }
  return <dialog className="data-dialog" ref={dialog} onCancel={onClose} aria-labelledby="import-title">
    <div className="section-heading"><h2 id="import-title">Bring a new day’s data</h2><button className="text-button" onClick={onClose}>Close</button></div>
    <p>Paste spreadsheet rows or open a CSV for each table. Use anonymous IDs only. Names, contact details and extra columns are rejected. Files are read on this device.</p>
    <label>Planning date<input type="date" value={today} disabled={reading} onChange={e => { setToday(e.target.value); setCandidate(null); }} /></label>
    <div className="input-tabs" role="group" aria-label="Import tables">{(["requests", "stock", "volunteers"] as const).map(t => <button key={t} aria-pressed={tab === t} onClick={() => setTab(t)}>{t[0].toUpperCase() + t.slice(1)}</button>)}</div>
    <p className="field-help">{tab === "requests" ? "Repeat a request ID on another row for another needed item. Keep its zone and priority the same." : tab === "volunteers" ? "Separate multiple zones with |, for example north|south. A header with no rows means no volunteers." : "Use a separate lot ID for each expiry date. A header with no rows means no stock."}</p>
    <textarea aria-label={`${tab} CSV`} value={sheets[tab]} rows={9} spellCheck={false} disabled={reading} onChange={e => change(tab, e.target.value)} />
    <label className="file-control">Open {tab} CSV<input type="file" accept=".csv,.tsv,text/csv,text/tab-separated-values" disabled={reading} onChange={e => { void readFile(e.target.files?.[0]); e.target.value = ""; }} /></label>
    <p className="field-help">Items: rice, milk, blankets, oats. Zones: north, east, south. Up to 100 requests, 100 lots and 30 volunteers. Units 1–100; priority 1–5; capacity 1–10.</p>
    {error && <p role="alert" className="run-status--error">{error}</p>}
    {candidate && <div className="import-summary" role="status"><strong>{candidate.requests.length} requests · {candidate.stock.length} stock lots · {candidate.volunteers.length} volunteers</strong><p>Checked for valid IDs, quantities, dates and catalogs. Loading replaces the current input and clears earlier decisions. The saved workspace is kept until you save again.</p></div>}
    <div className="snapshot-actions"><button className="secondary-button" disabled={reading} onClick={check}>Check all tables</button><button className="primary-button" disabled={reading || !candidate} onClick={() => candidate && onImport(candidate)}>Use checked data</button></div>
  </dialog>;
}
