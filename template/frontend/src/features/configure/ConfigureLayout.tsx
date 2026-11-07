import { PlugConnection, TagDollar } from "@gravity-ui/icons";
import { NavLink, Outlet } from "react-router";
import { cues } from "../../lib/sound";

const ITEMS = [
  { to: "providers", label: "Providers", icon: <PlugConnection /> },
  { to: "models", label: "Models & pricing", icon: <TagDollar /> },
];

export function ConfigureLayout() {
  return (
    <div className="grid gap-8 md:grid-cols-[12rem_minmax(0,1fr)]">
      <aside className="md:sticky md:top-[calc(var(--header-h)+var(--tabs-h)+1.75rem)] md:self-start">
        <div className="mb-2 px-2 text-xs font-medium text-muted">Configure</div>
        <nav className="subnav">
          {ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} className="subnav-item" {...cues.hover}>
              {item.icon}
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="min-w-0">
        <Outlet />
      </div>
    </div>
  );
}
