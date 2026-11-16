import { Check, Copy } from "@gravity-ui/icons";
import { useEffect, useRef, useState } from "react";
import { copyText } from "../lib/clipboard";
import { notify } from "../lib/notify";
import { Button, type ButtonSize } from "./Button";
import { cn } from "./cn";
import { Tooltip } from "./overlays";

/** Copy to clipboard; the icon turns into a check for a moment. Without `label` it is
 *  an icon button with a tooltip. `text` may be a function, read at click time. */
export function CopyButton({
  text,
  label,
  tooltip = "Copy",
  size = "xs",
  className,
}: {
  text: string | (() => string);
  label?: string;
  tooltip?: string;
  size?: ButtonSize;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);

  async function copy() {
    if (!(await copyText(typeof text === "function" ? text() : text))) {
      notify.error("Couldn’t copy to the clipboard.");
      return;
    }
    setCopied(true);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 1600);
  }

  const button = (
    <Button
      variant="ghost"
      size={size}
      icon={!label}
      className={cn("copy-btn", className)}
      data-copied={copied ? "" : undefined}
      aria-label={label ? undefined : tooltip}
      onClick={() => void copy()}
    >
      <span className="copy-swap" aria-hidden>
        <Copy />
        <Check />
      </span>
      {label && (
        <span className="copy-swap" aria-hidden>
          <span>{label}</span>
          <span>Copied</span>
        </span>
      )}
      {label && <span className="sr-only">{label}</span>}
      <span className="sr-only" aria-live="polite">
        {copied ? "Copied" : ""}
      </span>
    </Button>
  );
  return label ? button : <Tooltip content={copied ? "Copied" : tooltip}>{button}</Tooltip>;
}
