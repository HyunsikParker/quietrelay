import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { rolldown } from "rolldown";

const temporary = mkdtempSync(join(tmpdir(), "quietrelay-review-"));
try {
  const bundle = await rolldown({ input: { review: resolve("src/review.ts"), planner: resolve("src/planner.ts") }, platform: "node" });
  await bundle.write({ dir: temporary, format: "esm", entryFileNames: "[name].mjs" });
  await bundle.close();
  const { reviewText } = await import(pathToFileURL(join(temporary, "review.mjs")));
  const { initialPayload, selectedPreview } = await import(pathToFileURL(join(temporary, "planner.mjs")));
  const p = initialPayload(), result = selectedPreview(p);
  const approved = result.plan.allocations[0].request_id, held = result.plan.reviews[0].request_id;
  const decisions = { [approved]: "approved", [held]: "held" };
  const text = reviewText(p, result, decisions, "preview");
  assert.equal((text.match(/^req-\d+ \(source req-\d+\) \|/gm) || []).length, 5);
  p.requests.forEach((r, i) => assert.ok(text.includes(`req-${i + 1} (source ${r.request_id}) |`)));
  assert.equal((text.match(/AWAITING COORDINATOR REVIEW/g) || []).length, 3);
  assert.match(text, /FOLLOW-UP — NO STOCK RESERVED/);
  assert.match(text, /no model ran/);
  assert.match(text, /No volunteer dispatched/);
  assert.match(text, /INPUT STOCK/);
  assert.match(text, /INPUT VOLUNTEERS/);
  assert.match(text, /2026-08-22/);
  assert.throws(() => reviewText(p, result, { [held]: "approved" }, "preview"));
  assert.throws(() => reviewText(p, result, { [approved]: "held" }, "preview"));
  assert.throws(() => reviewText(p, result, { "req-999": "approved" }, "preview"));
  assert.match(reviewText(p, result, {}, "agent"), /verified local Strands agent result/);
  assert.equal((reviewText(p, result, {}, "preview").match(/AWAITING COORDINATOR REVIEW/g) || []).length, 5);
  p.stock[0].units = 6; p.volunteers[0].capacity = 3;
  assert.throws(() => reviewText(p, result, decisions, "preview"));
  assert.equal((reviewText(p, selectedPreview(p), {}, "preview").match(/AWAITING COORDINATOR REVIEW/g) || []).length, 5);
  console.log("Review export passed: complete snapshot, pending/approved/follow-up distinctions, undo, changed input and stale decisions.");
} finally { rmSync(temporary, { recursive: true, force: true }); }
