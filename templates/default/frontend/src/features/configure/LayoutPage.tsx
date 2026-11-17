import { Check } from "@gravity-ui/icons";
import { useRef, type KeyboardEvent } from "react";
import { useSaveSettings, useSettings } from "../../lib/hooks";
import { cues } from "../../lib/sound";
import type { NavPosition } from "../../lib/types";
import { PageHeader, SectionHeader, Skeleton } from "../../ui";

const OPTIONS: { value: NavPosition; title: string; description: string }[] = [
  {
    value: "top",
    title: "Top navigation",
    description: "Tabs in a header across the top. The page gets the full width.",
  },
  {
    value: "side",
    title: "Sidebar",
    description: "Pages listed down the left edge, grouped by section, with the account at the foot.",
  },
];

/** A miniature of each layout, drawn with the theme's own tokens. */
function Preview({ value }: { value: NavPosition }) {
  if (value === "top") {
    return (
      <div className="layout-preview" data-layout="top" aria-hidden="true">
        <div className="lp-bar">
          <span className="lp-mark" />
          <span className="lp-line w-10" />
          <span className="ml-auto lp-dot" />
        </div>
        <div className="lp-tabs">
          <span className="lp-tab" data-active="" />
          <span className="lp-tab" />
          <span className="lp-tab" />
          <span className="lp-tab" />
        </div>
        <div className="lp-body">
          <span className="lp-line w-16" />
          <div className="lp-cards">
            <span />
            <span />
            <span />
          </div>
          <span className="lp-block" />
        </div>
      </div>
    );
  }
  return (
    <div className="layout-preview" data-layout="side" aria-hidden="true">
      <div className="lp-rail">
        <div className="flex items-center gap-1">
          <span className="lp-mark" />
          <span className="lp-line w-8" />
        </div>
        <span className="lp-item" data-active="" />
        <span className="lp-item" />
        <span className="lp-item" />
        <span className="lp-item" />
        <span className="lp-item mt-auto" />
      </div>
      <div className="lp-sheet">
        <span className="lp-line w-16" />
        <div className="lp-cards">
          <span />
          <span />
          <span />
        </div>
        <span className="lp-block" />
      </div>
    </div>
  );
}

export function LayoutPage() {
  const settings = useSettings();
  const save = useSaveSettings();
  const current = settings.data?.nav_position;
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function choose(value: NavPosition) {
    if (value !== current) save.mutate({ nav_position: value });
  }

  // Radio group keys: arrows move and choose, like native radios.
  function onKeyDown(event: KeyboardEvent, index: number) {
    const step = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = (index + step + OPTIONS.length) % OPTIONS.length;
    refs.current[next]?.focus();
    choose(OPTIONS[next].value);
  }

  return (
    <>
      <PageHeader title="Layout" description="How the dashboard is arranged. It applies to everyone who signs in to this workspace." />
      <SectionHeader title="Navigation" meta="Below 768px the sidebar folds into the header" />
      {current === undefined ? (
        <div className="grid max-w-3xl gap-4 sm:grid-cols-2">
          <Skeleton className="h-64 rounded-[15px]" />
          <Skeleton className="h-64 rounded-[15px]" />
        </div>
      ) : (
        <div className="grid max-w-3xl gap-4 sm:grid-cols-2" role="radiogroup" aria-label="Navigation">
          {OPTIONS.map((option, index) => {
            const selected = option.value === current;
            return (
              <button
                key={option.value}
                ref={(el) => {
                  refs.current[index] = el;
                }}
                type="button"
                role="radio"
                aria-checked={selected}
                tabIndex={selected ? 0 : -1}
                className="layout-option"
                onClick={() => choose(option.value)}
                onKeyDown={(event) => onKeyDown(event, index)}
                {...cues.toggle}
              >
                <div className="layout-option-body">
                  <Preview value={option.value} />
                </div>
                <div className="layout-option-foot">
                  <span className="layout-radio" aria-hidden="true">
                    {selected && <Check width={10} height={10} />}
                  </span>
                  <span className="min-w-0 text-left">
                    <span className="block text-sm font-medium text-ink">{option.title}</span>
                    <span className="mt-0.5 block text-xs text-muted">{option.description}</span>
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </>
  );
}
