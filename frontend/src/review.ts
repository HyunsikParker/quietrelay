import type { AuthoritativePlan } from "./api";
import { validateResult, type Payload } from "./planner";

export type Decisions = Record<string, "approved" | "held">;

export function reviewText(payload: Payload, result: AuthoritativePlan, decisions: Decisions, mode: "agent" | "preview") {
  const verified = validateResult(payload, result);
  const ready = new Map(verified.plan.allocations.map(a => [a.request_id, a]));
  const unresolved = new Map(verified.plan.reviews.map(r => [r.request_id, r]));
  for (const [id, decision] of Object.entries(decisions)) {
    if (!(decision === "approved" ? ready.has(id) : decision === "held" && unresolved.has(id))) {
      throw new Error("A decision does not match this plan. Replan and review again.");
    }
  }
  const lines = ["QUIETRELAY — COORDINATOR REVIEW", "Synthetic sample only. No volunteer dispatched and no message or payment sent.",
    mode === "agent" ? "Source: verified local Strands agent result." : "Source: browser planning preview; no model ran.",
    `Scenario date: ${payload.today}.`, "This is a saved snapshot. Later edits and decisions are not included.", "", "REQUESTS"];
  payload.requests.forEach((r, i) => {
    const id = `req-${i + 1}`, allocation = ready.get(id), review = unresolved.get(id);
    const state = decisions[id] === "approved" ? "APPROVED LOCALLY" : decisions[id] === "held" ? "FOLLOW-UP — NO STOCK RESERVED" : "AWAITING COORDINATOR REVIEW";
    lines.push(`${id} | ${r.zone} | priority ${r.urgency} | ${state}`);
    lines.push(`  Needed: ${r.needs.map(n => `${n.units} ${n.item}`).join(", ")}`);
    if (allocation) lines.push(`  Planned: ${allocation.items.map(n => `${n.units} ${n.item} from ${n.lot_id}`).join(", ")} | ${allocation.volunteer_id}`);
    if (review) lines.push(`  Unresolved: ${review.reason.replaceAll("_", " ")}`, ...review.evidence.map(e => `  ${e}`));
  });
  lines.push("", "INPUT STOCK");
  payload.stock.forEach((s, i) => lines.push(`lot-${i + 1} | ${s.item} | ${s.units} units | expires ${s.expires_on}`));
  lines.push("", "INPUT VOLUNTEERS");
  payload.volunteers.forEach((v, i) => lines.push(`vol-${i + 1} | ${v.zones.join(", ")} | capacity ${v.capacity} requests`));
  return lines.join("\n") + "\n";
}
