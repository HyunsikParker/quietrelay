import { ArrowRight, CirclePlay, LoaderCircle, ShieldCheck } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import { ActivityLedger } from "./components/ActivityLedger";
import { Brand } from "./components/Brand";
import { DecisionPanel } from "./components/DecisionPanel";
import { MobileNav } from "./components/MobileNav";
import { PlanTable } from "./components/PlanTable";
import { Sidebar } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { runLocalPlan, type AuthoritativePlan } from "./api";
import { DEMO_PAYLOAD, INITIAL_LEDGER, INITIAL_ROWS, REQUEST_ZONES, SHORTAGE_REVIEW, type LedgerEntry, type PlanRow } from "./data";

export function App() {
  const [collapsed, setCollapsed] = useState(false);
  const [zone, setZone] = useState("All");
  const [selectedId, setSelectedId] = useState<string>(SHORTAGE_REVIEW.requestId);
  const [option, setOption] = useState<"hold" | "substitute">("hold");
  const [outcome, setOutcome] = useState<"held" | "substituted" | null>(null);
  const [sheetOpen, setSheetOpen] = useState(true);
  const [ledger, setLedger] = useState<LedgerEntry[]>(INITIAL_LEDGER);
  const [openLedgerId, setOpenLedgerId] = useState<string | null>(null);
  const [sourceRows, setSourceRows] = useState<PlanRow[]>(INITIAL_ROWS);
  const [agentState, setAgentState] = useState<"idle" | "running" | "ready" | "error" | "stale">("idle");
  const eventCounter = useRef(1);
  const outcomeRef = useRef<"held" | "substituted" | null>(null);
  const agentRunningRef = useRef(false);
  const decisionRevisionRef = useRef(0);

  const canonicalRows = useMemo<PlanRow[]>(
    () => sourceRows
      .map((row) => {
        if (row.id !== SHORTAGE_REVIEW.requestId || outcome === null) return row;
        if (outcome === "held") {
          return { ...row, allocation: `${SHORTAGE_REVIEW.need.item} · ${SHORTAGE_REVIEW.availableUnits} units held`, status: "Held" as const };
        }
        const shortageUnits = SHORTAGE_REVIEW.need.units - SHORTAGE_REVIEW.availableUnits;
        return { ...row, allocation: `${SHORTAGE_REVIEW.need.item} · ${SHORTAGE_REVIEW.availableUnits} + ${SHORTAGE_REVIEW.substitute.item} · ${shortageUnits}`, volunteer: SHORTAGE_REVIEW.volunteerId, status: "Ready" as const };
      }),
    [outcome, sourceRows],
  );
  const rows = useMemo(
    () => canonicalRows.filter((row) => zone === "All" || row.zone === zone),
    [canonicalRows, zone],
  );
  const readyCount = canonicalRows.filter((row) => row.status === "Ready").length;
  const unresolved = canonicalRows.filter((row) => row.status !== "Ready").length;
  const reviewTarget = canonicalRows.find((row) => row.status !== "Ready");

  function selectRow(row: PlanRow) {
    setSelectedId(row.id);
    if (row.id === SHORTAGE_REVIEW.requestId) setSheetOpen(true);
  }

  function rowsFromPlan(result: AuthoritativePlan): PlanRow[] {
    const expected = {
      "req-1": { volunteer: "vol-1", items: "lot-1:rice:2" },
      "req-2": { volunteer: "vol-2", items: "lot-2:milk:1" },
      "req-3": { volunteer: "vol-1", items: "lot-3:blankets:3" },
    } as const;
    if (result.plan.allocations.length !== 3 || result.plan.reviews.length !== 1) throw new Error();
    const rows = new Map<string, PlanRow>();
    for (const allocation of result.plan.allocations) {
      const zone = REQUEST_ZONES[allocation.request_id];
      const required = expected[allocation.request_id as keyof typeof expected];
      const itemSignature = allocation.items.map((item) => `${item.lot_id}:${item.item}:${item.units}`).join("|");
      if (!zone || !required || rows.has(allocation.request_id) || allocation.volunteer_id !== required.volunteer || itemSignature !== required.items) throw new Error();
      const items = allocation.items.map((item) => `${item.item[0].toUpperCase()}${item.item.slice(1)} · ${item.units} ${item.units === 1 ? "unit" : "units"}`);
      rows.set(allocation.request_id, { id: allocation.request_id, zone, allocation: items.join(" + "), volunteer: allocation.volunteer_id, status: "Ready" });
    }
    for (const review of result.plan.reviews) {
      const zone = REQUEST_ZONES[review.request_id];
      if (!zone || rows.has(review.request_id) || review.request_id !== SHORTAGE_REVIEW.requestId || review.reason !== "inventory_shortage" || review.evidence.length !== 1 || review.evidence[0] !== "rice: need 4, available 2") throw new Error();
      rows.set(review.request_id, { id: review.request_id, zone, allocation: `${SHORTAGE_REVIEW.need.item} · ${SHORTAGE_REVIEW.need.units} units`, volunteer: SHORTAGE_REVIEW.volunteerId, status: "Decision" });
    }
    const ordered = Object.keys(REQUEST_ZONES).map((id) => rows.get(id));
    if (ordered.some((row) => row === undefined)) throw new Error();
    return ordered as PlanRow[];
  }

  async function runAgent() {
    if (agentRunningRef.current) return;
    agentRunningRef.current = true;
    const decisionRevision = decisionRevisionRef.current;
    setAgentState("running");
    try {
      const result = await runLocalPlan(DEMO_PAYLOAD);
      const nextRows = rowsFromPlan(result);
      if (decisionRevisionRef.current !== decisionRevision) {
        setAgentState("stale");
        return;
      }
      outcomeRef.current = null;
      setOutcome(null);
      setOption("hold");
      setSourceRows(nextRows);
      setSelectedId(SHORTAGE_REVIEW.requestId);
      setSheetOpen(true);
      setLedger((current) => [...current, {
        id: `agent-${eventCounter.current++}`,
        time: "Now",
        label: "Local agent verified the plan",
        detail: `${result.plan.allocations.length} allocations are ready and ${result.plan.reviews.length} ${result.plan.reviews.length === 1 ? "decision remains" : "decisions remain"} local. No external action was sent.`,
      }]);
      setAgentState("ready");
    } catch {
      setAgentState("error");
    } finally {
      agentRunningRef.current = false;
    }
  }

  function approveDecision() {
    if (agentRunningRef.current || outcomeRef.current !== null) return;
    const shortageUnits = SHORTAGE_REVIEW.need.units - SHORTAGE_REVIEW.availableUnits;
    if (
      option === "substitute"
      && (!SHORTAGE_REVIEW.substitute.approved
        || SHORTAGE_REVIEW.substitute.availableUnits < shortageUnits
        || !SHORTAGE_REVIEW.volunteerId)
    ) return;
    const nextOutcome = option === "hold" ? "held" : "substituted";
    const id = `decision-${eventCounter.current++}`;
    outcomeRef.current = nextOutcome;
    decisionRevisionRef.current += 1;
    setOutcome(nextOutcome);
    setLedger((current) => [...current, {
      id,
      time: "Now",
      label: nextOutcome === "held" ? "Stock held for review" : "Approved substitute applied",
      detail: nextOutcome === "held"
        ? `${SHORTAGE_REVIEW.availableUnits} rice units are held. The request remains open. No external action was sent.`
        : `${shortageUnits} approved ${SHORTAGE_REVIEW.substitute.item.toLowerCase()} units complete the local allocation with ${SHORTAGE_REVIEW.volunteerId}. No external action was sent.`,
    }]);
    setSheetOpen(false);
  }

  function undoDecision() {
    if (agentRunningRef.current || outcomeRef.current === null) return;
    const id = `decision-${eventCounter.current++}`;
    outcomeRef.current = null;
    decisionRevisionRef.current += 1;
    setOutcome(null);
    setLedger((current) => [...current, {
      id,
      time: "Now",
      label: "Decision undone",
      detail: "The request returned to review. Earlier activity remains visible. No external action was sent.",
      review: true,
    }]);
  }

  return (
    <div className={`app-shell ${collapsed ? "app-shell--collapsed" : ""}`}>
      <Sidebar collapsed={collapsed} onCollapse={() => setCollapsed((value) => !value)} />
      <div className="mobile-header"><Brand /><ShieldCheck aria-label="Local privacy boundary" /></div>
      <TopBar zone={zone} onZoneChange={setZone} onMenu={() => setCollapsed((value) => !value)} />
      <main className="workspace">
        <section className="plan-workspace">
          <header className="plan-header">
            <h1>Today’s plan</h1>
            <p>{readyCount} clear {readyCount === 1 ? "match is" : "matches are"} ready. {unresolved === 0 ? "No decisions need you." : `${unresolved} ${unresolved === 1 ? "decision needs" : "decisions need"} you.`}</p>
            <div className="plan-actions">
              <button className="secondary-button agent-button" type="button" disabled={agentState === "running"} onClick={runAgent}>{agentState === "running" ? <LoaderCircle className="spin" aria-hidden="true" /> : <CirclePlay aria-hidden="true" />}{agentState === "ready" ? "Run again" : agentState === "running" ? "Verifying locally" : "Run local agent"}</button>
              <button className="primary-button review-button" type="button" disabled={!reviewTarget} onClick={() => { if (reviewTarget) { setSelectedId(reviewTarget.id); setSheetOpen(true); } }}>{reviewTarget ? "Review decisions" : "No decisions pending"}<ArrowRight aria-hidden="true" /></button>
            </div>
            <p className={`agent-status agent-status--${agentState}`} role="status">{agentState === "ready" ? "Model digest verified. The authoritative plan is shown below." : agentState === "error" ? "Local verification is unavailable. Check Ollama, then try again." : agentState === "stale" ? "The decision changed during verification. Run the local agent again." : "Runs on 127.0.0.1. Source identifiers never reach the model."}</p>
          </header>
          <PlanTable rows={rows} selectedId={selectedId} onSelect={selectRow} />
        </section>
        <ActivityLedger entries={ledger} openId={openLedgerId} onToggle={(id) => setOpenLedgerId((current) => current === id ? null : id)} />
      </main>
      <DecisionPanel busy={agentState === "running"} outcome={outcome} option={option} onOptionChange={setOption} onApprove={approveDecision} onUndo={undoDecision} onClose={() => setSheetOpen(false)} />
      {sheetOpen && selectedId === SHORTAGE_REVIEW.requestId ? <div className="mobile-sheet"><DecisionPanel busy={agentState === "running"} mobile outcome={outcome} option={option} onOptionChange={setOption} onApprove={approveDecision} onUndo={undoDecision} onClose={() => setSheetOpen(false)} /></div> : null}
      <MobileNav />
    </div>
  );
}
