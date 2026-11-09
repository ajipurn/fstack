import { useId, useMemo, useState } from "react";
import { cn } from "./cn";

export type Bar = { key: string; label: string; value: number; hint?: string };

/**
 * Dependency-free column chart. Bars grow in on mount, ease to new values,
 * and a hairline guide + label follow the pointer. Monochrome by design.
 */
export function BarChart({
  data,
  format,
  height = 160,
  className,
}: {
  data: Bar[];
  format: (value: number) => string;
  height?: number;
  className?: string;
}) {
  const id = useId();
  const [hover, setHover] = useState<number | null>(null);
  const max = useMemo(() => Math.max(...data.map((d) => d.value), 0), [data]);
  const scale = max > 0 ? max : 1;
  const ticks = [1, 0.5, 0];
  const focus = hover ?? null;

  return (
    <div className={cn("relative select-none", className)}>
      <div className="flex items-baseline justify-between pb-3">
        <div className="text-xs text-muted">
          {focus !== null ? data[focus]?.label : `${data[0]?.label ?? ""} – ${data[data.length - 1]?.label ?? ""}`}
        </div>
        <div className="mono text-xs tabular-nums text-ink-2">
          {focus !== null ? (data[focus]?.hint ?? format(data[focus]?.value ?? 0)) : `peak ${format(max)}`}
        </div>
      </div>
      <div className="relative" style={{ height }} onPointerLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <div
            key={t}
            className="pointer-events-none absolute inset-x-0 border-t border-dashed border-line"
            style={{ top: `${(1 - t) * 100}%` }}
          />
        ))}
        <div className="absolute inset-0 flex items-end gap-[3px]" role="img" aria-labelledby={`${id}-desc`}>
          {data.map((d, i) => {
            const pct = (d.value / scale) * 100;
            const dim = focus !== null && focus !== i;
            return (
              <div
                key={d.key}
                className="group relative flex h-full flex-1 items-end"
                onPointerEnter={() => setHover(i)}
              >
                <div
                  className="w-full origin-bottom rounded-t-[3px] bg-ink/85 transition-[height,opacity] duration-500 ease-[var(--ease-out)] [animation:bar-grow_600ms_var(--ease-out)_both] dark:bg-ink/80"
                  style={{
                    height: d.value > 0 ? `max(${pct}%, 2px)` : "1px",
                    opacity: d.value > 0 ? (dim ? 0.28 : 1) : 0.25,
                    animationDelay: `${Math.min(i * 12, 300)}ms`,
                  }}
                />
              </div>
            );
          })}
        </div>
      </div>
      <p id={`${id}-desc`} className="sr-only">
        {data.map((d) => `${d.label}: ${format(d.value)}`).join(", ")}
      </p>
    </div>
  );
}

/** Inline proportion bar for ranked lists. */
export function Meter({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.max(2, (value / max) * 100) : 0;
  return (
    <div className="h-1 w-full overflow-hidden rounded-full bg-surface-3">
      <div
        className="h-full rounded-full bg-ink/70 transition-[width] duration-500 ease-[var(--ease-out)]"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
