import { BadgeCheck, Box, CalendarDays, CheckCircle2, Users, X } from "lucide-react";

import { SHORTAGE_REVIEW } from "../data";

type DecisionPanelProps = {
  busy: boolean;
  mobile?: boolean;
  outcome: "held" | "substituted" | null;
  option: "hold" | "substitute";
  onOptionChange: (option: "hold" | "substitute") => void;
  onApprove: () => void;
  onUndo: () => void;
  onClose: () => void;
};

export function DecisionPanel({ busy, mobile = false, outcome, option, onOptionChange, onApprove, onUndo, onClose }: DecisionPanelProps) {
  const recorded = outcome !== null;
  const radioName = mobile ? "decision-mobile" : "decision-desktop";
  const shortageUnits = SHORTAGE_REVIEW.need.units - SHORTAGE_REVIEW.availableUnits;
  const substituteAvailable = SHORTAGE_REVIEW.substitute.approved
    && SHORTAGE_REVIEW.substitute.availableUnits >= shortageUnits;
  return (
    <aside className={mobile ? "decision-panel decision-panel--sheet" : "decision-panel"} aria-label="Decision evidence">
      {mobile ? <div className="sheet-handle" aria-hidden="true" /> : null}
      <div className="decision-title-row">
        <div><h2>{recorded ? "Decision recorded" : `${SHORTAGE_REVIEW.need.item} shortage`}</h2><p>{SHORTAGE_REVIEW.requestId}</p></div>
        {mobile ? <button className="icon-button close-sheet" type="button" onClick={onClose} aria-label="Close decision"><X /></button> : null}
      </div>
      {recorded ? (
        <div className="approved-state" role="status">
          <CheckCircle2 aria-hidden="true" />
          <h3>{outcome === "held" ? "Stock held safely" : "Local plan updated"}</h3>
          <p>{outcome === "held" ? `${SHORTAGE_REVIEW.availableUnits} rice units are held. The request remains open and reversible.` : `The approved ${SHORTAGE_REVIEW.substitute.item.toLowerCase()} substitute completes the local plan. No message, purchase, or dispatch was sent.`}</p>
          <button className="secondary-button" type="button" disabled={busy} onClick={onUndo}>Undo decision</button>
        </div>
      ) : (
        <>
          <section className="evidence-section">
            <h3>Evidence</h3>
            <ul>
              <li><Box aria-hidden="true" /><span>Need {SHORTAGE_REVIEW.need.units} units · {SHORTAGE_REVIEW.availableUnits} available</span></li>
              <li><CalendarDays aria-hidden="true" /><span>Earliest expiry {SHORTAGE_REVIEW.earliestExpiry}</span></li>
              <li><BadgeCheck aria-hidden="true" /><span>{SHORTAGE_REVIEW.substitute.item} approved · {SHORTAGE_REVIEW.substitute.availableUnits} available</span></li>
              <li><Users aria-hidden="true" /><span>{SHORTAGE_REVIEW.volunteerId} available</span></li>
            </ul>
          </section>
          <fieldset className="decision-options" disabled={busy}>
            <legend>Decision options</legend>
            <label className={option === "hold" ? "option-row option-row--selected" : "option-row"}>
              <input type="radio" name={radioName} checked={option === "hold"} onChange={() => onOptionChange("hold")} />
              <span>Hold available stock</span>
            </label>
            <label className={option === "substitute" ? "option-row option-row--selected" : "option-row"}>
              <input type="radio" name={radioName} checked={option === "substitute"} disabled={!substituteAvailable} onChange={() => onOptionChange("substitute")} />
              <span>Use approved substitute</span>
            </label>
          </fieldset>
          <div className="decision-actions">
            <button className="primary-button" type="button" disabled={busy} onClick={onApprove}>Approve decision<Chevron /></button>
            <button className="secondary-button" type="button" onClick={onClose}>Keep pending</button>
          </div>
        </>
      )}
    </aside>
  );
}

function Chevron() {
  return <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m6 3 7 7-7 7M12.5 10H2" /></svg>;
}
