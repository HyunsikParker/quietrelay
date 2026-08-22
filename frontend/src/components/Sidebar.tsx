import { CalendarDays, ClipboardList, Package, ShieldCheck, Users, PanelLeftClose } from "lucide-react";

import { Brand } from "./Brand";

const items = [
  { label: "Today", icon: CalendarDays },
  { label: "Requests", icon: ClipboardList },
  { label: "Inventory", icon: Package },
  { label: "Volunteers", icon: Users },
  { label: "Policy", icon: ShieldCheck },
] as const;

type SidebarProps = {
  collapsed: boolean;
  onCollapse: () => void;
};

export function Sidebar({ collapsed, onCollapse }: SidebarProps) {
  return (
    <aside className={collapsed ? "sidebar sidebar--collapsed" : "sidebar"}>
      <Brand />
      <nav aria-label="Primary navigation">
        {items.map(({ label, icon: Icon }) => (
          <button className={label === "Today" ? "nav-item nav-item--active" : "nav-item"} key={label} type="button" aria-current={label === "Today" ? "page" : undefined} disabled={label !== "Today"}>
            <Icon aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </nav>
      <button className="collapse-control" type="button" onClick={onCollapse} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
        <PanelLeftClose aria-hidden="true" />
        <span>{collapsed ? "Open" : "Collapse"}</span>
      </button>
    </aside>
  );
}
