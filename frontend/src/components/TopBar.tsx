import { Bell, Menu, UserRound } from "lucide-react";

type TopBarProps = {
  zone: string;
  onZoneChange: (zone: string) => void;
  onMenu: () => void;
};

export function TopBar({ zone, onZoneChange, onMenu }: TopBarProps) {
  return (
    <header className="topbar">
      <button className="icon-button" type="button" onClick={onMenu} aria-label="Toggle navigation">
        <Menu aria-hidden="true" />
      </button>
      <div className="topbar-actions">
        <button className="icon-button" type="button" aria-label="Notifications" disabled>
          <Bell aria-hidden="true" />
        </button>
        <label className="zone-select">
          <span>Zone view:</span>
          <select value={zone} onChange={(event) => onZoneChange(event.target.value)} aria-label="Zone view">
            <option value="All">All</option>
            <option value="North">North</option>
            <option value="East">East</option>
            <option value="South">South</option>
          </select>
        </label>
        <button className="icon-button account-button" type="button" aria-label="Local demo account" disabled>
          <UserRound aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}

