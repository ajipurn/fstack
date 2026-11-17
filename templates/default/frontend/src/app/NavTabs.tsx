import { Fragment, useLayoutEffect, useRef, useState, type CSSProperties, type PointerEvent, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router";
import { cues } from "../lib/sound";

/** `group` labels a run of tabs in the sidebar (the header ignores it). */
export type Tab = { to: string; label: string; icon?: ReactNode; end?: boolean; group?: string };
export type Orientation = "horizontal" | "vertical";

type Box = { x: number; y: number; w: number; h: number };
type Hover = { box: Box; visible: boolean; instant: boolean };

function measure(container: HTMLElement, el: HTMLElement | null): Box | null {
  if (!el) return null;
  const a = container.getBoundingClientRect();
  const b = el.getBoundingClientRect();
  return { x: b.left - a.left + container.scrollLeft, y: b.top - a.top + container.scrollTop, w: b.width, h: b.height };
}

/** Horizontal: the pill slides along x, the underline sits 10px in from each side.
 *  Vertical: both slide along y and span the full width; the indicator is a raised chip. */
function hoverStyle(box: Box, vertical: boolean): CSSProperties {
  return vertical ? { height: box.h, transform: `translateY(${box.y}px)` } : { width: box.w, transform: `translateX(${box.x}px)` };
}

function indicatorStyle(box: Box | null, vertical: boolean): CSSProperties {
  if (!box) return vertical ? { height: 0 } : { width: 0 };
  return vertical ? hoverStyle(box, true) : { width: box.w - 20, transform: `translateX(${box.x + 10}px)` };
}

/**
 * Clerk-style navigation, as a tab row in the header or a list in the sidebar. A hover
 * pill glides between items (it fades in where the pointer enters, then slides); the
 * active indicator springs to the current route. Each is one element animating
 * transform + size — interruptible.
 */
export function NavTabs({ tabs, orientation = "horizontal" }: { tabs: Tab[]; orientation?: Orientation }) {
  const ref = useRef<HTMLElement>(null);
  const { pathname } = useLocation();
  const [active, setActive] = useState<Box | null>(null);
  const [settled, setSettled] = useState(false);
  const [hover, setHover] = useState<Hover | null>(null);
  const vertical = orientation === "vertical";

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
      data-orientation={orientation}
      aria-label="Main"
      onPointerLeave={() => setHover((prev) => prev && { ...prev, visible: false })}
    >
      <span
        className="nav-hover"
        aria-hidden="true"
        data-visible={hover?.visible ? "" : undefined}
        data-instant={hover?.instant ? "" : undefined}
        style={hover ? hoverStyle(hover.box, vertical) : undefined}
      />
      {tabs.map((tab, index) => (
        <Fragment key={tab.to}>
          {vertical && tab.group && tab.group !== tabs[index - 1]?.group && <div className="nav-group">{tab.group}</div>}
          <NavLink to={tab.to} end={tab.end} className="nav-tab" onPointerEnter={enter} {...cues.hover}>
            {tab.icon}
            <span className="truncate">{tab.label}</span>
          </NavLink>
        </Fragment>
      ))}
      <span
        className="nav-indicator"
        aria-hidden="true"
        data-instant={settled ? undefined : ""}
        style={indicatorStyle(active, vertical)}
      />
    </nav>
  );
}
