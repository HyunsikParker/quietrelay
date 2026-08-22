import { CalendarDays, ClipboardList, Ellipsis, Package } from "lucide-react";

const items = [
  { label: "Today", icon: CalendarDays },
  { label: "Requests", icon: ClipboardList },
  { label: "Inventory", icon: Package },
  { label: "More", icon: Ellipsis },
] as const;

export function MobileNav() {
  return (
    <nav className="mobile-nav" aria-label="Mobile navigation">
      {items.map(({ label, icon: Icon }) => (
        <button className={label === "Today" ? "mobile-nav-item mobile-nav-item--active" : "mobile-nav-item"} type="button" key={label} disabled={label !== "Today"}>
          <Icon aria-hidden="true" /><span>{label}</span>
        </button>
      ))}
    </nav>
  );
}
