import { validateInput, type Payload } from "./planner";

export type Sheets = { requests: string; stock: string; volunteers: string };
const HEADERS = {
  requests: ["request_id", "zone", "priority", "item", "units"],
  stock: ["lot_id", "item", "units", "expires_on"],
  volunteers: ["volunteer_id", "zones", "capacity"],
};

/** Accept CSV or pasted spreadsheet cells. Free-text columns are never retained. */
function table(text: string, kind: keyof Sheets): string[][] {
  if (text.length > 80_000) throw new Error(`${kind}: file exceeds 80 KB.`);
  text = text.replace(/^\uFEFF/, "").replaceAll("\r\n", "\n");
  const delimiter = text.split("\n")[0].includes("\t") ? "\t" : ",";
  const rows: string[][] = [];
  let row: string[] = [], cell = "", quoted = false, closed = false;
  const endCell = () => { row.push(cell.trim()); cell = ""; closed = false; };
  const endRow = () => { endCell(); if (row.some(c => c !== "")) rows.push(row); row = []; };
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (c === '"') { quoted = false; closed = true; }
      else cell += c;
    } else if (c === delimiter) endCell();
    else if (c === "\n") endRow();
    else if (c === '"' && !cell && !closed) quoted = true;
    else if (closed || c === '"') throw new Error(`${kind}: invalid quoting near row ${rows.length + 1}.`);
    else cell += c;
    if (cell.length > 100 || rows.length > 401) throw new Error(`${kind}: too many rows or an unsupported cell.`);
  }
  if (quoted) throw new Error(`${kind}: an unfinished quoted cell was found.`);
  if (cell || row.length || closed) endRow();
  const header = rows.shift();
  if (!header || header.join("|") !== HEADERS[kind].join("|")) throw new Error(`${kind}: use the exact template column headings. Extra columns are not accepted.`);
  for (const [i, cells] of rows.entries()) if (cells.length !== header.length) throw new Error(`${kind}: row ${i + 2} has the wrong number of cells.`);
  return rows;
}

function number(cell: string, kind: string, row: number) {
  if (!/^[0-9]+$/.test(cell)) throw new Error(`${kind}: use whole positive numbers in row ${row + 2}.`);
  return Number(cell);
}

export function parseSheets(today: string, sheets: Sheets): Payload {
  const p: Payload = { today, requests: [], stock: [], volunteers: [] };
  const byId = new Map<string, Payload["requests"][number]>();
  for (const [i, [id, zone, urgency, item, units]] of table(sheets.requests, "requests").entries()) {
    const priority = number(urgency, "requests", i);
    const existing = byId.get(id);
    if (existing && (existing.zone !== zone || existing.urgency !== priority)) throw new Error(`requests: repeated ID in row ${i + 2} has a different zone or priority.`);
    const r = existing ?? { request_id: id, zone, urgency: priority, needs: [] };
    r.needs.push({ item, units: number(units, "requests", i) });
    if (!existing) { byId.set(id, r); p.requests.push(r); }
  }
  p.stock = table(sheets.stock, "stock").map(([lot_id, item, units, expires_on], i) => ({ lot_id, item, units: number(units, "stock", i), expires_on }));
  p.volunteers = table(sheets.volunteers, "volunteers").map(([volunteer_id, zones, capacity], i) => ({ volunteer_id, zones: zones.split("|"), capacity: number(capacity, "volunteers", i) }));
  validateInput(p);
  return p;
}

export function payloadSheets(p: Payload): Sheets {
  validateInput(p);
  return {
    requests: [HEADERS.requests.join(","), ...p.requests.flatMap(r => r.needs.map(n => [r.request_id, r.zone, r.urgency, n.item, n.units].join(",")))].join("\n"),
    stock: [HEADERS.stock.join(","), ...p.stock.map(s => [s.lot_id, s.item, s.units, s.expires_on].join(","))].join("\n"),
    volunteers: [HEADERS.volunteers.join(","), ...p.volunteers.map(v => [v.volunteer_id, v.zones.join("|"), v.capacity].join(","))].join("\n"),
  };
}
