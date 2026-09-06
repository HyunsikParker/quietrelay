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
