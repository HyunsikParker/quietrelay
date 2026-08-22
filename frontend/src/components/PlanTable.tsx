import { AlertCircle, Check, ChevronRight } from "lucide-react";

import type { PlanRow } from "../data";

type PlanTableProps = {
  rows: PlanRow[];
  selectedId: string;
  onSelect: (row: PlanRow) => void;
};

function Status({ status }: Pick<PlanRow, "status">) {
  if (status === "Ready") return (
    <span className="status status--ready"><Check aria-hidden="true" />Ready</span>
  );
  if (status === "Held") return (
    <span className="status status--held"><AlertCircle aria-hidden="true" />Held</span>
  );
  return (
    <span className="status status--decision"><AlertCircle aria-hidden="true" />Decision</span>
  );
}

export function PlanTable({ rows, selectedId, onSelect }: PlanTableProps) {
  return (
    <div className="plan-table" role="table" aria-label="Today’s allocations">
      <div className="plan-table-head" role="row">
        <span role="columnheader">Request</span><span role="columnheader">Zone</span><span role="columnheader">Allocation</span><span role="columnheader">Volunteer</span><span role="columnheader">Status</span><span aria-hidden="true" />
      </div>
      {rows.map((row) => (
        <button className={`plan-row ${row.id === selectedId ? "plan-row--selected" : ""} ${row.status === "Decision" ? "plan-row--review" : ""}`} key={row.id} type="button" role="row" onClick={() => onSelect(row)}>
          <span className="request-id" role="cell">{row.id}</span>
          <span role="cell">{row.zone}</span>
          <span role="cell">{row.allocation}</span>
          <span className="volunteer-id" role="cell">{row.volunteer}</span>
          <span role="cell"><Status status={row.status} /></span>
          <ChevronRight className="row-chevron" aria-hidden="true" />
        </button>
      ))}
    </div>
  );
}
