import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { rolldown } from "rolldown";

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const root = resolve(frontend, "..");
const cases = JSON.parse(readFileSync(join(frontend, "tests/scenarios.json"), "utf8"));
// Expanded intake: canonical handles cross 9, split lots, multi-item requests,
// empty resources, and both sides of the expiry boundary.
let seed = 9102026;
const pick = n => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed % n; };
const items = ["rice", "milk", "blankets", "oats"], zones = ["north", "east", "south"];
for (let sample = 0; sample < 60; sample++) {
  const payload = { today: "2026-09-10",
    requests: Array.from({ length: 1 + pick(100) }, (_, i) => ({ request_id: `req-${1000 + i}`, zone: zones[pick(3)], urgency: 1 + pick(5), needs: items.slice(0, 1 + pick(4)).map(item => ({ item, units: 1 + pick(10) })) })),
    stock: Array.from({ length: sample === 0 ? 0 : 1 + pick(100) }, (_, i) => ({ lot_id: `lot-${2000 + i}`, item: items[pick(4)], units: 1 + pick(20), expires_on: ["2026-09-09", "2026-09-10", "2026-09-11"][pick(3)] })),
    volunteers: Array.from({ length: sample === 1 ? 0 : 1 + pick(30) }, (_, i) => ({ volunteer_id: `vol-${3000 + i}`, zones: zones.slice(0, 1 + pick(3)), capacity: 1 + pick(10) })) };
  cases.push({ name: `expanded-${sample}`, payload });
}
cases.push({ name: "one-request-100-lots", payload: { today: "2026-09-10", requests: [{ request_id: "req-900", zone: "north", urgency: 5, needs: [{ item: "rice", units: 100 }] }], stock: Array.from({ length: 100 }, (_, i) => ({ lot_id: `lot-${i + 1}`, item: "rice", units: 1, expires_on: "2026-09-10" })), volunteers: [{ volunteer_id: "vol-800", zones: ["north"], capacity: 1 }] } });
cases.push({ name: "maximum-supported-input", payload: { today: "2026-09-10", requests: Array.from({ length: 100 }, (_, i) => ({ request_id: `req-${1000 + i}`, zone: zones[i % 3], urgency: 5, needs: items.map(item => ({ item, units: 100 })) })), stock: Array.from({ length: 100 }, (_, i) => ({ lot_id: `lot-${2000 + i}`, item: items[i % 4], units: 100, expires_on: "2026-09-10" })), volunteers: Array.from({ length: 30 }, (_, i) => ({ volunteer_id: `vol-${3000 + i}`, zones, capacity: 10 })) } });
for (const c of cases) assert.ok(Buffer.byteLength(JSON.stringify(c.payload)) <= 65536, "frontend inputs fit the backend size limit");
const expected = JSON.parse(execFileSync(process.env.QUIETRELAY_TEST_PYTHON || join(root, ".venv/bin/python"), ["-c", `
import json,sys
from quietrelay.agent import plan_payload
from quietrelay.rank1_candidate_v2 import authoritative_plan_v2
print(json.dumps([{
 "control":json.loads(plan_payload(json.dumps(c["payload"]))),
 "recovery":json.loads(authoritative_plan_v2(json.dumps(c["payload"])))
} for c in json.load(sys.stdin)]))
`], { cwd: root, input: JSON.stringify(cases), encoding: "utf8" }));
const temporary = mkdtempSync(join(tmpdir(), "quietrelay-planner-test-"));
try {
  const bundle = await rolldown({ input: join(frontend, "src/planner.ts"), platform: "node" });
  const output = join(temporary, "planner.mjs");
  await bundle.write({ file: output, format: "esm" });
  await bundle.close();
  const { initialPayload, previewPlan, selectedPreview, validateResult, validateInput } = await import(pathToFileURL(output).href);
  for (const [i, scenario] of cases.entries()) {
    const actual = selectedPreview(scenario.payload);
    assert.deepEqual(actual, expected[i].recovery, `scenario ${i}: browser/Python recovery`);
    assert.deepEqual(previewPlan(scenario.payload, false).plan, expected[i].control, `scenario ${i}: control`);
    validateResult(scenario.payload, actual);
    const bad = structuredClone(actual);
    bad.plan.reviews.push({ request_id: "req-999", reason: "inventory_shortage", evidence: [] });
    assert.throws(() => validateResult(scenario.payload, bad), `scenario ${i}: unknown request`);
  }
  const p = initialPayload();
  assert.equal(previewPlan(p, false).plan.allocations.length, 3);
  assert.equal(selectedPreview(p).plan.allocations.length, 4);
  const old = selectedPreview(p);
  p.stock[0].units = 6;
  p.volunteers[0].capacity = 3;
  assert.equal(selectedPreview(p).plan.allocations.length, 5);
  assert.throws(() => validateResult(p, old), "old result must not bind to new input");
  const changed = selectedPreview(p);
  changed.plan.allocations[0].items[0].units += 1;
  assert.throws(() => validateResult(p, changed), "over-allocation must be rejected");
  for (const invalid of [0, -1, 101, 1.5, NaN, Infinity]) {
    const p = initialPayload(); p.stock[0].units = invalid;
    assert.throws(() => validateInput(p), `invalid quantity ${invalid}`);
  }
  console.log(`${cases.length} cross-language scenarios passed; stale results, unknown requests, over-allocation and invalid inputs rejected.`);
} finally {
  rmSync(temporary, { recursive: true, force: true });
}
