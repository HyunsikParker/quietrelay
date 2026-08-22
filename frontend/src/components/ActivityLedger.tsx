import { AlertCircle, CheckCircle2, ChevronDown } from "lucide-react";

import type { LedgerEntry } from "../data";

type ActivityLedgerProps = {
  entries: LedgerEntry[];
  openId: string | null;
  onToggle: (id: string) => void;
};

export function ActivityLedger({ entries, openId, onToggle }: ActivityLedgerProps) {
  return (
    <section className="activity-ledger">
      <div className="ledger-heading"><h2>Activity ledger</h2><button type="button" className="text-button" onClick={() => onToggle("*")} aria-expanded={openId === "*"}>View full ledger<ChevronDown className={openId === "*" ? "ledger-chevron ledger-chevron--open" : "ledger-chevron"} /></button></div>
      <div>
        {entries.map((entry) => {
          const isOpen = openId === "*" || openId === entry.id;
          return (
            <button className="ledger-row" type="button" key={entry.id} onClick={() => onToggle(entry.id)} aria-expanded={isOpen}>
              {entry.review ? <AlertCircle className="ledger-review" /> : <CheckCircle2 className="ledger-ready" />}
              <time>{entry.time}</time><span className="ledger-dot">·</span><span>{entry.label}</span><ChevronDown className={isOpen ? "ledger-chevron ledger-chevron--open" : "ledger-chevron"} />
              {isOpen ? <small>{entry.detail}</small> : null}
            </button>
          );
        })}
      </div>
    </section>
  );
}
