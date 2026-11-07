import { OverlayScrollbarsComponent, useOverlayScrollbars } from "overlayscrollbars-react";
import { useEffect, type ComponentPropsWithoutRef } from "react";

type Axis = "vertical" | "horizontal" | "both";

const scrollbars = {
  theme: "os-theme-app",
  autoHide: "move" as const,
  autoHideDelay: 700,
  autoHideSuspend: true,
  clickScroll: true,
};

function overflow(axis: Axis) {
  return {
    x: axis === "vertical" ? ("hidden" as const) : ("scroll" as const),
    y: axis === "horizontal" ? ("hidden" as const) : ("scroll" as const),
  };
}

/** Thin overlay scrollbars that don't shift layout. */
export function ScrollArea({ axis = "vertical", ...props }: ComponentPropsWithoutRef<"div"> & { axis?: Axis }) {
  return <OverlayScrollbarsComponent {...props} defer options={{ overflow: overflow(axis), scrollbars }} />;
}

/** Page-level scrollbars on <body>. Mount once. */
export function BodyScrollbars() {
  const [initialize, instance] = useOverlayScrollbars({
    options: { overflow: { x: "hidden", y: "scroll" }, scrollbars },
  });
  useEffect(() => {
    initialize({ target: document.body, cancel: { body: null } });
    return () => instance()?.destroy();
  }, [initialize, instance]);
  return null;
}
