import { parseAuthoritativePlan, type AuthoritativePlan } from "./api";

export type ExecutionMode = "live" | "replay";

type LocationLike = Pick<Location, "hostname" | "search">;

const VERIFIED_REPLAY_PLAN = {
  external_actions: [],
  plan: {
    allocations: [
      { request_id: "req-1", volunteer_id: "vol-3", items: [{ lot_id: "lot-1", item: "rice", units: 2 }] },
      { request_id: "req-2", volunteer_id: "vol-2", items: [{ lot_id: "lot-2", item: "milk", units: 1 }] },
      { request_id: "req-3", volunteer_id: "vol-1", items: [{ lot_id: "lot-3", item: "blankets", units: 3 }] },
      { request_id: "req-5", volunteer_id: "vol-1", items: [{ lot_id: "lot-4", item: "oats", units: 1 }] },
    ],
    reviews: [
      { request_id: "req-4", reason: "inventory_shortage", evidence: ["rice: need 4, available 2"] },
    ],
  },
} satisfies AuthoritativePlan;

export function resolveExecutionMode(location: LocationLike): ExecutionMode {
  const requestedMode = new URLSearchParams(location.search).get("mode");
  if (requestedMode === "replay") return "replay";
  const hostname = location.hostname.toLowerCase();
  return hostname === "127.0.0.1" || hostname === "localhost" || hostname === "::1" ? "live" : "replay";
}

export function getVerifiedReplayPlan(): AuthoritativePlan {
  return parseAuthoritativePlan(structuredClone(VERIFIED_REPLAY_PLAN));
}
