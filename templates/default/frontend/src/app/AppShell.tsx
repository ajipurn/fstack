import {
  ArrowRightFromSquare,
  ArrowUpRightFromSquare,
  ChartColumn,
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
import { useQuery } from "@tanstack/react-query";
import { Outlet, useLocation } from "react-router";
import { get } from "../lib/api";
import { keys } from "../lib/query";
import { useSoundEnabled } from "../lib/sound";
import { useTheme } from "../lib/theme";
import type { Health } from "../lib/types";
import { Button, Menu, Tooltip } from "../ui";
import { NavTabs, type Tab } from "./NavTabs";
import { useSignOut } from "./session";

const APP_NAME = "Fstack Starter";

const TABS: Tab[] = [
  { to: "/", label: "Overview", icon: <House />, end: true },
  { to: "/run", label: "Run", icon: <Play /> },
  { to: "/prompts", label: "Prompts", icon: <FileText /> },
  { to: "/usage", label: "Usage", icon: <ChartColumn /> },
  { to: "/configure", label: "Configure", icon: <Gear /> },
];

function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 16 16" width="12" height="12" fill="none">
        <path d="M5 12V4h6M5 8h4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

function useHealth() {
  return useQuery({ queryKey: keys.health, queryFn: () => get<Health>("/health") });
}

function AccountMenu() {
  const signOut = useSignOut();
  const [theme, toggleTheme] = useTheme();
  const [sound, toggleSound] = useSoundEnabled();
  // The API only serves /api/docs outside production.
  const docs = useHealth().data?.environment !== "production";
  return (
    <Menu
      trigger={
        <button
          type="button"
          className="grid size-7 place-items-center rounded-full bg-surface-3 text-ink-2 shadow-[inset_0_0_0_1px_var(--line-2)] transition-transform active:scale-95"
          aria-label="Account"
        >
          <Person width={14} height={14} />
        </button>
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

export function AppShell() {
  const { pathname } = useLocation();
  const [theme, toggleTheme] = useTheme();
  const section = pathname.split("/")[1] ?? "";
  return (
    <div className="min-h-dvh">
      <header className="app-header">
        <div className="app-header-inner">
          <div className="app-topbar">
            <a href="/" className="crumb -ml-2 gap-2.5">
              <BrandMark />
              <span className="font-semibold tracking-[-0.01em]">{APP_NAME}</span>
            </a>
            <div className="flex-1" />
            <Tooltip content={theme === "dark" ? "Light mode" : "Dark mode"} side="bottom">
              <Button variant="ghost" size="sm" icon onClick={toggleTheme} aria-label="Toggle theme">
                {theme === "dark" ? <Sun /> : <Moon />}
              </Button>
            </Tooltip>
            <AccountMenu />
          </div>
          <NavTabs tabs={TABS} />
        </div>
      </header>
      <main key={section} className="page route-enter">
        <Outlet />
      </main>
    </div>
  );
}
