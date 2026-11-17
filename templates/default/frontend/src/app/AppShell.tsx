import {
  ArrowRightFromSquare,
  ArrowUpRightFromSquare,
  ChartColumn,
  ChevronsExpandVertical,
  FileText,
  Gear,
  House,
  Moon,
  Person,
  Play,
  Sun,
  Volume,
  VolumeXmark,
} from "@gravity-ui/icons";
import { Outlet, useLocation } from "react-router";
import { useHealth, useSettings } from "../lib/hooks";
import { useMediaQuery } from "../lib/media";
import { useSoundEnabled } from "../lib/sound";
import { useTheme } from "../lib/theme";
import { Button, Dot, Menu, Tooltip } from "../ui";
import { APP_NAME } from "./brand";
import { BrandMark } from "./BrandMark";
import { NavTabs, type Tab } from "./NavTabs";
import { useSignOut } from "./session";

const TABS: Tab[] = [
  { to: "/", label: "Overview", icon: <House />, end: true, group: "Workspace" },
  { to: "/run", label: "Run", icon: <Play />, group: "Workspace" },
  { to: "/prompts", label: "Prompts", icon: <FileText />, group: "Workspace" },
  { to: "/usage", label: "Usage", icon: <ChartColumn />, group: "Workspace" },
  { to: "/configure", label: "Configure", icon: <Gear />, group: "Settings" },
];

const ENVIRONMENT: Record<string, string> = { production: "Production", development: "Development", test: "Test" };

function AccountMenu({ inSidebar }: { inSidebar?: boolean }) {
  const signOut = useSignOut();
  const [theme, toggleTheme] = useTheme();
  const [sound, toggleSound] = useSoundEnabled();
  // The API only serves /api/docs outside production.
  const docs = useHealth().data?.environment !== "production";
  const avatar = (
    <span className="account-avatar" aria-hidden="true">
      <Person width={14} height={14} />
    </span>
  );
  return (
    <Menu
      side={inSidebar ? "top" : "bottom"}
      align={inSidebar ? "start" : "end"}
      trigger={
        inSidebar ? (
          <button type="button" className="account-card" aria-label="Account">
            {avatar}
            <span className="min-w-0 flex-1 text-left">
              <span className="block truncate text-sm font-medium text-ink">Access key</span>
              <span className="block truncate text-[11px] text-muted">Signed in</span>
            </span>
            <ChevronsExpandVertical className="account-card-chevron" width={14} height={14} />
          </button>
        ) : (
          <button type="button" className="account-trigger" aria-label="Account">
            {avatar}
          </button>
        )
      }
      header={
        <div className="px-2 pb-2 pt-1.5">
          <div className="truncate text-sm font-medium">Signed in with access key</div>
          <div className="text-xs text-muted">A new key signs every browser out.</div>
        </div>
      }
      items={[
        { separator: true },
        {
          label: theme === "dark" ? "Light mode" : "Dark mode",
          icon: theme === "dark" ? <Sun /> : <Moon />,
          onSelect: toggleTheme,
        },
        {
          label: sound ? "Mute sounds" : "Enable sounds",
          icon: sound ? <VolumeXmark /> : <Volume />,
          onSelect: toggleSound,
        },
        ...(docs
          ? [
              {
                label: "API reference",
                icon: <ArrowUpRightFromSquare />,
                onSelect: () => window.open("/api/docs", "_blank", "noopener"),
              },
            ]
          : []),
        { separator: true },
        { label: "Sign out", icon: <ArrowRightFromSquare />, onSelect: () => signOut.mutate() },
      ]}
    />
  );
}

function ThemeToggle({ side }: { side: "bottom" | "top" }) {
  const [theme, toggleTheme] = useTheme();
  return (
    <Tooltip content={theme === "dark" ? "Light mode" : "Dark mode"} side={side}>
      <Button variant="ghost" size="sm" icon onClick={toggleTheme} aria-label="Toggle theme">
        {theme === "dark" ? <Sun /> : <Moon />}
      </Button>
    </Tooltip>
  );
}

/** Brand, actions and a row of tabs, stuck to the top. */
function Header() {
  return (
    <header className="app-header">
      <div className="app-header-inner">
        <div className="app-topbar">
          <a href="/" className="crumb brand-link -ml-2 gap-2.5">
            <BrandMark />
            <span className="truncate font-semibold tracking-[-0.01em]">{APP_NAME}</span>
          </a>
          <div className="flex-1" />
          <ThemeToggle side="bottom" />
          <AccountMenu />
        </div>
        <NavTabs tabs={TABS} />
      </div>
    </header>
  );
}

/** The workspace down the left edge: brand and environment, grouped tabs, the account. */
function Sidebar() {
  const health = useHealth();
  const environment = health.data?.environment;
  return (
    <aside className="app-sidebar">
      <a href="/" className="sidebar-brand">
        <BrandMark size="md" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold tracking-[-0.01em] text-ink">{APP_NAME}</span>
          <span className="flex items-center gap-1.5 text-[11px] text-muted">
            <Dot tone={health.isError ? "danger" : environment ? "ok" : "neutral"} />
            <span className="truncate">{environment ? (ENVIRONMENT[environment] ?? environment) : "Connecting…"}</span>
          </span>
        </span>
      </a>
      <NavTabs tabs={TABS} orientation="vertical" />
      <div className="sidebar-foot">
        <AccountMenu inSidebar />
        <ThemeToggle side="top" />
      </div>
    </aside>
  );
}

export function AppShell() {
  const { pathname } = useLocation();
  // Configure → Layout picks it for the workspace; below `md` a sidebar folds into the header.
  const position = useSettings().data?.nav_position ?? "top";
  const wide = useMediaQuery("(min-width: 48rem)");
  const nav = position === "side" && wide ? "side" : "top";
  const section = pathname.split("/")[1] ?? "";
  // Only the bar swaps when the layout changes: the page in .app-content stays mounted.
  return (
    <div className="app-shell" data-nav={nav}>
      {nav === "side" ? <Sidebar /> : <Header />}
      <div className="app-content">
        <main key={section} className="page route-enter">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
