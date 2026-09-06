import { parseAuthoritativePlan, type AuthoritativePlan } from "./api";
import { DEMO_PAYLOAD } from "./data";

export type Payload = {
  today: string;
  requests: { request_id: string; zone: string; urgency: number; needs: { item: string; units: number }[] }[];
  stock: { lot_id: string; item: string; units: number; expires_on: string }[];
  volunteers: { volunteer_id: string; zones: string[]; capacity: number }[];
};
export const initialPayload = (): Payload => structuredClone(DEMO_PAYLOAD) as unknown as Payload;
const compare = (a: string, b: string) => a < b ? -1 : a > b ? 1 : 0;

/** Same bounded synthetic form is accepted by the local agent. No user text is sent. */
export function validateInput(p: Payload) {
  const integer = (n: number, max: number) => Number.isSafeInteger(n) && n >= 1 && n <= max;
  const date = (s: string) => /^\d{4}-\d{2}-\d{2}$/.test(s) && Number.isFinite(Date.parse(s)) && new Date(s).toISOString().slice(0, 10) === s;
  const zones = ["north", "east", "south"];
  const items = ["rice", "milk", "blankets", "oats"];
  if (!date(p.today) || p.requests.length !== 5 || p.stock.length !== 4 || p.volunteers.length !== 3) throw new Error("Invalid scenario.");
  if (p.requests.some(r => !zones.includes(r.zone) || !integer(r.urgency, 5) || r.needs.length !== 1 || r.needs.some(n => !items.includes(n.item) || !integer(n.units, 100)))) throw new Error("Request quantities must be whole numbers from 1 to 100.");
  if (p.stock.some(s => !items.includes(s.item) || !integer(s.units, 100) || !date(s.expires_on))) throw new Error("Check stock quantities and expiry dates.");
  if (p.volunteers.some(v => !integer(v.capacity, 10) || !v.zones.length || v.zones.some(z => !zones.includes(z)))) throw new Error("Volunteer capacity must be a whole number from 1 to 10.");
}

/** Deterministic preview of the agent's tools, never an LLM invocation. */
export function previewPlan(p: Payload, recovery = true): AuthoritativePlan {
  validateInput(p);
  const requests = p.requests.map((r, i) => ({ ...r, request_id: `req-${i + 1}` })).sort((a, b) => b.urgency - a.urgency || compare(a.request_id, b.request_id));
  const stock = p.stock.map((s, i) => ({ ...s, lot_id: `lot-${i + 1}` })).filter(s => s.expires_on >= p.today).sort((a, b) => compare(a.expires_on, b.expires_on) || compare(a.lot_id, b.lot_id));
  const remaining = new Map(stock.map(s => [s.lot_id, s.units]));
  const slots = p.volunteers.flatMap((v, i) => Array.from({ length: v.capacity }, (_, slot) => ({ key: `vol-${i + 1}/${slot}`, id: `vol-${i + 1}`, zones: v.zones })));
  const adjacency = new Map(requests.map(r => [r.request_id, slots.filter(s => s.zones.includes(r.zone))]));
  const occupant = new Map<string, string>();
  const assignment = new Map<string, string>();
  const plan: AuthoritativePlan = { external_actions: [], plan: { allocations: [], reviews: [] } };
  for (const r of requests) {
    const shortages = r.needs.flatMap(n => {
      const available = stock.filter(s => s.item === n.item).reduce((sum, s) => sum + remaining.get(s.lot_id)!, 0);
      return available < n.units ? [`${n.item}: need ${n.units}, available ${available}`] : [];
    });
    if (shortages.length) { plan.plan.reviews.push({ request_id: r.request_id, reason: "inventory_shortage", evidence: shortages }); continue; }
    const queue = [r.request_id], seenRequests = new Set(queue), seenSlots = new Set<string>(), parent = new Map<string, string>();
    let free: string | undefined;
    while (queue.length && !free) {
      const current = queue.shift()!;
      for (const slot of adjacency.get(current)!) {
        if (seenSlots.has(slot.key)) continue;
        seenSlots.add(slot.key); parent.set(slot.key, current);
        const other = occupant.get(slot.key);
        if (!other) { free = slot.key; break; }
        if (recovery && !seenRequests.has(other)) { seenRequests.add(other); queue.push(other); }
      }
    }
    if (!free) { plan.plan.reviews.push({ request_id: r.request_id, reason: "volunteer_capacity", evidence: [`no ${recovery ? "incremental matching" : "remaining volunteer"} capacity for zone ${r.zone}`] }); continue; }
    while (free) {
      const current = parent.get(free)!;
      const previous = assignment.get(current);
      occupant.set(free, current); assignment.set(current, free); free = previous;
    }
    const allocated: AuthoritativePlan["plan"]["allocations"][number]["items"] = [];
    for (const n of r.needs) {
      let needed = n.units;
      for (const s of stock.filter(s => s.item === n.item)) {
        const take = Math.min(needed, remaining.get(s.lot_id)!);
        if (take) { allocated.push({ lot_id: s.lot_id, item: n.item, units: take }); remaining.set(s.lot_id, remaining.get(s.lot_id)! - take); needed -= take; }
        if (!needed) break;
      }
    }
    plan.plan.allocations.push({ request_id: r.request_id, volunteer_id: "", items: allocated });
  }
  for (const a of plan.plan.allocations) a.volunteer_id = assignment.get(a.request_id)!.split("/")[0];
  return plan;
}

export function selectedPreview(p: Payload) {
  const baseline = previewPlan(p, false), recovery = previewPlan(p, true);
  return recovery.plan.allocations.length > baseline.plan.allocations.length ? recovery : baseline;
}

export function validateResult(p: Payload, raw: unknown): AuthoritativePlan {
  const result = parseAuthoritativePlan(raw);
  // Bind every row, unit, assignment and review to the exact submitted input.
  const normalize = (r: AuthoritativePlan) => JSON.stringify({ allocations: r.plan.allocations.map(a => [a.request_id, a.volunteer_id, a.items.map(i => [i.lot_id, i.item, i.units])]), reviews: r.plan.reviews.map(r => [r.request_id, r.reason, r.evidence]) });
  if (normalize(result) !== normalize(selectedPreview(p))) throw new Error("The result does not match this input. No plan was applied.");
  return result;
}
