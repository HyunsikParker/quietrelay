import type { AuthoritativePlan } from "./api";
import { validateInput, validateResult, type Payload } from "./planner";
import { validateDecisions, type Decisions } from "./review";

export const WORKSPACE_KEY = "quietrelay.workspace.v1";
export const MAX_WORKSPACE_BYTES = 256_000;
export type Workspace = {
  version: 1;
  savedAt: string;
  payload: Payload;
  result: AuthoritativePlan | null;
  decisions: Decisions;
};

/** A saved plan is revalidated as data; it never proves a fresh model run. */
export function parseWorkspace(text: string): Workspace {
  if (text.length > MAX_WORKSPACE_BYTES) throw new Error("Workspace is too large.");
  let value: Workspace;
  try { value = JSON.parse(text); } catch { throw new Error("This file is not a readable workspace."); }
  if (!value || typeof value !== "object" || Array.isArray(value)
    || Object.keys(value).sort().join("|") !== "decisions|payload|result|savedAt|version"
    || value.version !== 1 || typeof value.savedAt !== "string" || value.savedAt.length > 32
    || !Number.isFinite(Date.parse(value.savedAt))) throw new Error("This workspace format is not supported.");
  validateInput(value.payload);
  if (value.result !== null) validateDecisions(validateResult(value.payload, value.result), value.decisions);
  else if (!value.decisions || typeof value.decisions !== "object" || Array.isArray(value.decisions) || Object.keys(value.decisions).length) throw new Error("Unplanned inputs cannot contain approvals.");
  return value;
}

export function serializeWorkspace(payload: Payload, result: AuthoritativePlan | null, decisions: Decisions, now = new Date()): string {
  const text = JSON.stringify({ version: 1, savedAt: now.toISOString(), payload, result, decisions });
  parseWorkspace(text);
  return text;
}

export function readSavedWorkspace(storage: Pick<Storage, "getItem">): Workspace | null {
  const text = storage.getItem(WORKSPACE_KEY);
  return text === null ? null : parseWorkspace(text);
}

/** Report success only after readback; storage denial leaves current work intact. */
export function writeSavedWorkspace(storage: Pick<Storage, "getItem" | "setItem">, text: string) {
  parseWorkspace(text);
  storage.setItem(WORKSPACE_KEY, text);
  if (storage.getItem(WORKSPACE_KEY) !== text) throw new Error("The browser could not confirm that your workspace was saved.");
}
