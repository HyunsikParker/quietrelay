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

export const ITEMS = ["rice", "milk", "blankets", "oats"];
export const ZONES = ["north", "east", "south"];
export const LIMITS = { requests: 100, stock: 100, volunteers: 30, units: 100, capacity: 10 };

function record(value: unknown, keys: string[]): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).sort().join("|") === [...keys].sort().join("|");
}

/** Validate the complete import boundary, including unknown fields and IDs. */
export function validateInput(p: Payload) {
  const integer = (n: number, max: number) => Number.isSafeInteger(n) && n >= 1 && n <= max;
  const date = (s: string) => typeof s === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s) && !s.startsWith("0000") && Number.isFinite(Date.parse(s)) && new Date(s).toISOString().slice(0, 10) === s;
  const handle = (s: string, prefix: string) => typeof s === "string" && new RegExp(`^${prefix}-[0-9]{1,4}$`).test(s);
  if (!record(p, ["today", "requests", "stock", "volunteers"]) || !date(p.today)) throw new Error("Use a valid planning date and only the expected data fields.");
  if (!Array.isArray(p.requests) || !p.requests.length || p.requests.length > LIMITS.requests
    || !Array.isArray(p.stock) || p.stock.length > LIMITS.stock
    || !Array.isArray(p.volunteers) || p.volunteers.length > LIMITS.volunteers) throw new Error("Use 1–100 requests, up to 100 stock lots and up to 30 volunteers.");
  if (p.requests.some(r => !record(r, ["request_id", "zone", "urgency", "needs"]) || !handle(r.request_id, "req") || !ZONES.includes(r.zone) || !integer(r.urgency, 5)
    || !Array.isArray(r.needs) || !r.needs.length || r.needs.length > ITEMS.length
    || r.needs.some(n => !record(n, ["item", "units"]) || !ITEMS.includes(n.item) || !integer(n.units, LIMITS.units))
    || new Set(r.needs.map(n => n.item)).size !== r.needs.length)) throw new Error("Each request needs a req-number ID, a zone, priority 1–5 and distinct items with 1–100 whole units.");
  if (p.stock.some(s => !record(s, ["lot_id", "item", "units", "expires_on"]) || !handle(s.lot_id, "lot") || !ITEMS.includes(s.item) || !integer(s.units, LIMITS.units) || !date(s.expires_on))) throw new Error("Each stock lot needs a lot-number ID, a supported item, 1–100 whole units and a valid expiry date.");
  if (p.volunteers.some(v => !record(v, ["volunteer_id", "zones", "capacity"]) || !handle(v.volunteer_id, "vol") || !integer(v.capacity, LIMITS.capacity)
    || !Array.isArray(v.zones) || !v.zones.length || v.zones.length > ZONES.length || v.zones.some(z => !ZONES.includes(z)) || new Set(v.zones).size !== v.zones.length)) throw new Error("Each volunteer needs a vol-number ID, distinct supported zones and capacity 1–10.");
  if (new Set(p.requests.map(r => r.request_id)).size !== p.requests.length || new Set(p.stock.map(s => s.lot_id)).size !== p.stock.length || new Set(p.volunteers.map(v => v.volunteer_id)).size !== p.volunteers.length) throw new Error("IDs must be unique within requests, stock lots and volunteers.");
}

/** Deterministic preview of the agent's tools, never an LLM invocation. */
export function previewPlan(p: Payload, recovery = true): AuthoritativePlan {
  validateInput(p);
  const requests = p.requests.map((r, i) => ({ ...r, request_id: `req-${i + 1}` })).sort((a, b) => b.urgency - a.urgency || compare(a.request_id, b.request_id));
  const stock = p.stock.map((s, i) => ({ ...s, lot_id: `lot-${i + 1}` })).filter(s => s.expires_on >= p.today).sort((a, b) => compare(a.expires_on, b.expires_on) || compare(a.lot_id, b.lot_id));
  const remaining = new Map(stock.map(s => [s.lot_id, s.units]));
  const slots = p.volunteers.map((v, i) => ({ ...v, id: `vol-${i + 1}` })).sort((a, b) => compare(a.id, b.id))
    .flatMap(v => Array.from({ length: v.capacity }, (_, slot) => ({ key: `${v.id}/${slot}`, id: v.id, zones: v.zones })));
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
