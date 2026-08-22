export type AuthoritativePlan = {
  external_actions: [];
  plan: {
    allocations: Array<{
      request_id: string;
      volunteer_id: string;
      items: Array<{ lot_id: string; item: string; units: number }>;
    }>;
    reviews: Array<{ request_id: string; reason: string; evidence: string[] }>;
  };
};

const MAX_RESPONSE_CHARACTERS = 1024 * 1024;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, keys: string[]) {
  return Object.keys(value).sort().join("|") === [...keys].sort().join("|");
}

function isShortHandle(value: unknown, prefix: string) {
  return typeof value === "string" && new RegExp(`^${prefix}-[0-9]{1,4}$`).test(value);
}

function parsePlan(value: unknown): AuthoritativePlan {
  if (!isRecord(value) || !hasExactKeys(value, ["external_actions", "plan"])) throw new Error();
  if (!Array.isArray(value.external_actions) || value.external_actions.length !== 0) throw new Error();
  if (!isRecord(value.plan) || !hasExactKeys(value.plan, ["allocations", "reviews"])) throw new Error();
  if (!Array.isArray(value.plan.allocations) || !Array.isArray(value.plan.reviews)) throw new Error();
  if (value.plan.allocations.length > 4 || value.plan.reviews.length > 1) throw new Error();
  for (const allocation of value.plan.allocations) {
    if (!isRecord(allocation) || !hasExactKeys(allocation, ["request_id", "volunteer_id", "items"])) throw new Error();
    if (!isShortHandle(allocation.request_id, "req") || !isShortHandle(allocation.volunteer_id, "vol") || !Array.isArray(allocation.items) || allocation.items.length > 4) throw new Error();
    for (const item of allocation.items) {
      if (!isRecord(item) || !hasExactKeys(item, ["lot_id", "item", "units"])) throw new Error();
      if (!isShortHandle(item.lot_id, "lot") || !["blankets", "milk", "oats", "rice"].includes(String(item.item)) || !Number.isSafeInteger(item.units) || Number(item.units) <= 0) throw new Error();
    }
  }
  for (const review of value.plan.reviews) {
    if (!isRecord(review) || !hasExactKeys(review, ["request_id", "reason", "evidence"])) throw new Error();
    if (!isShortHandle(review.request_id, "req") || !["inventory_shortage", "volunteer_capacity"].includes(String(review.reason)) || !Array.isArray(review.evidence) || review.evidence.length > 4 || !review.evidence.every((item) => typeof item === "string" && item.length <= 160)) throw new Error();
  }
  return value as AuthoritativePlan;
}

export async function runLocalPlan(payload: unknown): Promise<AuthoritativePlan> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 52_000);
  try {
    const response = await fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      referrerPolicy: "no-referrer",
      signal: controller.signal,
    });
    if (!response.ok || !response.headers.get("Content-Type")?.startsWith("application/json")) throw new Error();
    const text = await response.text();
    if (text.length > MAX_RESPONSE_CHARACTERS) throw new Error();
    return parsePlan(JSON.parse(text));
  } finally {
    window.clearTimeout(timer);
  }
}
