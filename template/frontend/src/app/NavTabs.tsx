import { useLayoutEffect, useRef, useState, type PointerEvent, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router";
import { cues } from "../lib/sound";

export type Tab = { to: string; label: string; icon?: ReactNode; end?: boolean };

type Box = { x: number; w: number };
type Hover = { box: Box; visible: boolean; instant: boolean };

function measure(container: HTMLElement, el: HTMLElement | null): Box | null {
  if (!el) return null;
  const a = container.getBoundingClientRect();
  const b = el.getBoundingClientRect();
  return { x: b.left - a.left + container.scrollLeft, w: b.width };
}

/**
 * Clerk-style tab row. A hover pill glides between tabs (it fades in where the
 * pointer enters, then slides); the active underline springs to the current
 * route. Each is one element animating transform + width — interruptible.
 */
export function NavTabs({ tabs }: { tabs: Tab[] }) {
  const ref = useRef<HTMLElement>(null);
  const { pathname } = useLocation();
  const [active, setActive] = useState<Box | null>(null);
  const [settled, setSettled] = useState(false);
  const [hover, setHover] = useState<Hover | null>(null);

  useLayoutEffect(() => {
    const nav = ref.current;
    if (!nav) return;
    const update = () => setActive(measure(nav, nav.querySelector<HTMLElement>('[aria-current="page"]')));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(nav);
    void document.fonts?.ready.then(update);
    return () => observer.disconnect();
  }, [pathname]);

  // The first position snaps; every change after that animates.
  useLayoutEffect(() => {
    if (!active || settled) return;
    const frame = requestAnimationFrame(() => setSettled(true));
    return () => cancelAnimationFrame(frame);
  }, [active, settled]);

  function enter(event: PointerEvent<HTMLAnchorElement>) {
    const nav = ref.current;
    const box = nav && measure(nav, event.currentTarget);
    if (box) setHover((prev) => ({ box, visible: true, instant: !prev?.visible }));
  }

  return (
    <nav
      ref={ref}
      className="nav-tabs"
      aria-label="Main"
      onPointerLeave={() => setHover((prev) => prev && { ...prev, visible: false })}
    >
      <span
        className="nav-hover"
        aria-hidden="true"
        data-visible={hover?.visible ? "" : undefined}
        data-instant={hover?.instant ? "" : undefined}
        style={hover ? { width: hover.box.w, transform: `translateX(${hover.box.x}px)` } : undefined}
      />
      {tabs.map((tab) => (
        <NavLink key={tab.to} to={tab.to} end={tab.end} className="nav-tab" onPointerEnter={enter} {...cues.hover}>
          {tab.icon}
          {tab.label}
        </NavLink>
      ))}
      <span
        className="nav-indicator"
        aria-hidden="true"
        data-instant={settled ? undefined : ""}
        style={active ? { width: active.w - 20, transform: `translateX(${active.x + 10}px)` } : { width: 0 }}
      />
    </nav>
  );
}
