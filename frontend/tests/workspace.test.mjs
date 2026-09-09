import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { rolldown } from "rolldown";
const temporary = mkdtempSync(join(tmpdir(), "quietrelay-workspace-"));
try {
  const bundle = await rolldown({ input: Object.fromEntries(["intake", "workspace", "planner"].map(n => [n, resolve(`src/${n}.ts`)])), platform: "node" });
  await bundle.write({ dir: temporary, format: "esm", entryFileNames: "[name].mjs" }); await bundle.close();
  const { initialPayload, selectedPreview, validateInput } = await import(pathToFileURL(join(temporary, "planner.mjs")));
  const { parseSheets, payloadSheets } = await import(pathToFileURL(join(temporary, "intake.mjs")));
  const { parseWorkspace, serializeWorkspace, writeSavedWorkspace, readSavedWorkspace } = await import(pathToFileURL(join(temporary, "workspace.mjs")));
  const p = initialPayload(); p.requests[0].request_id = "req-987";
  p.requests[0].needs.push({ item: "oats", units: 2 });
  const sheets = payloadSheets(p);
  assert.deepEqual(parseSheets(p.today, sheets), p);
  assert.deepEqual(parseSheets(p.today, Object.fromEntries(Object.entries(sheets).map(([k, v]) => [k, "\uFEFF" + v.split("\n").map(row => row.split(",").map(c => `"${c}"`).join(",")).join("\r\n")]))), p);
  assert.deepEqual(parseSheets(p.today, Object.fromEntries(Object.entries(sheets).map(([k,v]) => [k,v.replaceAll(",", "\t")]))), p);
  const empty = parseSheets(p.today, { ...sheets, stock: "lot_id,item,units,expires_on", volunteers: "volunteer_id,zones,capacity" });
  assert.equal(selectedPreview(empty).plan.allocations.length, 0);
  for (const bad of [sheets.requests.replace("request_id,", "name,"), sheets.requests.replace("req-987", "Jane Doe"), sheets.requests.replace(/,2($|\n)/, ",=1+1$1"), sheets.requests + '\n"unfinished', sheets.requests + "\nreq-987,south,1,rice,2", sheets.requests + "\nreq-987,north,5,rice,2"]) {
    assert.throws(() => parseSheets(p.today, { ...sheets, requests: bad }));
  }
  for (const mutate of [q => { q.requests[0].name = "unsupported"; }, q => { q.requests.push(q.requests[0]); }, q => { q.volunteers[0].zones = ["north", "north"]; }, q => { q.today = "2026-02-30"; }, q => { q.stock[0].expires_on = "0000-01-01"; }, q => { q.requests = Array.from({length:101}, (_,i) => ({...q.requests[0], request_id:`req-${i}`})); }]) {
    const q = structuredClone(p); mutate(q); assert.throws(() => validateInput(q));
  }
  const result = selectedPreview(p), id = result.plan.allocations[0].request_id;
  const text = serializeWorkspace(p, result, { [id]: "approved" });
  const restored = parseWorkspace(text);
  assert.deepEqual(restored.payload, p); assert.deepEqual(restored.result, result); assert.equal(restored.decisions[id], "approved");
  for (const mutate of [q => { q.payload.stock[0].units = 100; }, q => { q.result.plan.allocations[0].items[0].units++; }, q => { q.decisions["req-999"] = "approved"; }, q => { q.result = null; }, q => { q.version = 2; }, q => { q.extra = true; }, q => { q.decisions[id] = "dispatched"; }]) {
    const q = JSON.parse(text); mutate(q); assert.throws(() => parseWorkspace(JSON.stringify(q)));
  }
  let stored = null;
  const storage = { setItem(_k, v) { stored = v; }, getItem() { return stored; } };
  assert.equal(readSavedWorkspace(storage), null); writeSavedWorkspace(storage, text); assert.deepEqual(readSavedWorkspace(storage), restored);
  assert.throws(() => writeSavedWorkspace({ getItem() { return null; }, setItem() {} }, text));
  assert.throws(() => writeSavedWorkspace({ getItem() { return null; }, setItem() { throw new Error("QuotaExceededError"); } }, text));
  assert.deepEqual(parseWorkspace(serializeWorkspace(p, null, {})).decisions, {});
  console.log("Intake/workspace passed: CSV/TSV, source IDs, multi-item requests, empty resources, hostile fields, stale/tampered plans, decisions and failed storage readback.");
} finally { rmSync(temporary, { recursive: true, force: true }); }
