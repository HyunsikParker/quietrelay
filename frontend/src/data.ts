export type PlanStatus = "Ready" | "Decision" | "Held";

export type PlanRow = {
  id: string;
  zone: "North" | "East" | "South";
  allocation: string;
  volunteer: string;
  status: PlanStatus;
};

export const SHORTAGE_REVIEW = {
  requestId: "req-4",
  need: { item: "Rice", units: 4 },
  availableUnits: 2,
  earliestExpiry: "Aug 23",
  substitute: { item: "Oats", approved: true, availableUnits: 2 },
  volunteerId: "vol-09",
} as const;

export const INITIAL_ROWS: PlanRow[] = [
  { id: "req-1", zone: "North", allocation: "Rice · 2 units", volunteer: "vol-1", status: "Ready" },
  { id: "req-2", zone: "East", allocation: "Milk · 1 unit", volunteer: "vol-2", status: "Ready" },
  { id: "req-3", zone: "North", allocation: "Blankets · 3 units", volunteer: "vol-1", status: "Ready" },
  { id: SHORTAGE_REVIEW.requestId, zone: "South", allocation: "Rice · 4 units", volunteer: SHORTAGE_REVIEW.volunteerId, status: "Decision" },
  { id: "req-5", zone: "South", allocation: "Oats · 1 unit", volunteer: "Unassigned", status: "Decision" },
];

export type LedgerEntry = {
  id: string;
  time: string;
  label: string;
  detail: string;
  review?: boolean;
};

export const INITIAL_LEDGER: LedgerEntry[] = [
  { id: "stock", time: "08:42", label: "Stock matched by earliest expiry", detail: "lot-1 expires Aug 23 and was evaluated first." },
  { id: "capacity", time: "08:43", label: "Submitted control reached volunteer capacity", detail: "req-5 remains a local decision until a safe reassignment is validated." },
  { id: "review", time: "08:44", label: "Human review requested", detail: "req-4 needs two more units, so the request entered review.", review: true },
  { id: "substitute", time: "08:45", label: "Control substitute availability recorded", detail: "At control time, two oats units and vol-09 are available for req-4. Recovery recalculates remaining stock." },
];

export const DEMO_PAYLOAD = {
  today: "2026-08-22",
  requests: [
    { request_id: "req-101", zone: "north", urgency: 5, needs: [{ item: "rice", units: 2 }] },
    { request_id: "req-102", zone: "east", urgency: 4, needs: [{ item: "milk", units: 1 }] },
    { request_id: "req-103", zone: "north", urgency: 3, needs: [{ item: "blankets", units: 3 }] },
    { request_id: "req-104", zone: "south", urgency: 2, needs: [{ item: "rice", units: 4 }] },
    { request_id: "req-105", zone: "south", urgency: 1, needs: [{ item: "oats", units: 1 }] },
  ],
  stock: [
    { lot_id: "lot-201", item: "rice", units: 4, expires_on: "2026-08-23" },
    { lot_id: "lot-202", item: "milk", units: 1, expires_on: "2026-08-24" },
    { lot_id: "lot-203", item: "blankets", units: 3, expires_on: "2026-09-01" },
    { lot_id: "lot-204", item: "oats", units: 2, expires_on: "2026-08-26" },
  ],
  volunteers: [
    { volunteer_id: "vol-301", zones: ["north", "south"], capacity: 2 },
    { volunteer_id: "vol-302", zones: ["east"], capacity: 1 },
    { volunteer_id: "vol-303", zones: ["north"], capacity: 1 },
  ],
} as const;

export const REQUEST_ZONES: Record<string, PlanRow["zone"]> = {
  "req-1": "North",
  "req-2": "East",
  "req-3": "North",
  "req-4": "South",
  "req-5": "South",
};
