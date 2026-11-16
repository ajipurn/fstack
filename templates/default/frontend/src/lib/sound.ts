import { bind, play as cue, setEnabled, setVolume, type SoundName } from "cuelume";
import { useCallback, useSyncExternalStore } from "react";

const KEY = "fstack-starter:sound";
const EVENT = "app:sound";

/** Spread on controls: `<button {...cues.press}>`. `bind()` wires them up. */
export const cues = {
  press: { "data-cuelume-press": "", "data-cuelume-release": "" },
  toggle: { "data-cuelume-toggle": "" },
  hover: { "data-cuelume-hover": "tick" },
  nav: { "data-cuelume-press": "page" },
} as const;

/** Off until the viewer turns it on. */
function read(): boolean {
  try {
    return localStorage.getItem(KEY) === "on";
  } catch {
    return false;
  }
}

export function initSound() {
  setEnabled(read());
  setVolume(0.55);
  bind();
}

export function play(name: SoundName) {
  if (read()) cue(name);
}

export function useSoundEnabled(): [boolean, () => void] {
  const enabled = useSyncExternalStore(
    (onChange) => {
      window.addEventListener(EVENT, onChange);
      return () => window.removeEventListener(EVENT, onChange);
    },
    read,
  );
  const toggle = useCallback(() => {
    const next = !read();
    try {
      localStorage.setItem(KEY, next ? "on" : "off");
    } catch {
      /* private mode */
    }
    setEnabled(next);
    if (next) cue("toggle");
    window.dispatchEvent(new Event(EVENT));
  }, []);
  return [enabled, toggle];
}
