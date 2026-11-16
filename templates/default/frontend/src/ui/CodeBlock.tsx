import { ChevronDown } from "@gravity-ui/icons";
import { Fragment, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { highlight, segment, type Mark, type Token } from "../lib/highlight";
import { cues } from "../lib/sound";
import { cn } from "./cn";
import { CopyButton } from "./CopyButton";
import type { Tone } from "./surfaces";

/** Taller blocks start folded to about this height (px). */
const FOLDED = 288;

/**
 * A titled, highlighted, copyable block of text (prompts, model output, JSON).
 * `marks` outline the spans that came from template inputs, with a legend on top.
 */
export function CodeBlock({
  title,
  icon,
  tone = "neutral",
  text,
  marks,
  badge,
  className,
}: {
  title: ReactNode;
  icon?: ReactNode;
  tone?: Tone;
  text: string;
  marks?: Mark[];
  /** Small note next to the title, e.g. "formatted". */
  badge?: ReactNode;
  className?: string;
}) {
  const tokens = useMemo(() => highlight(text), [text]);
  const parts = useMemo(() => (marks?.length ? segment(tokens, marks.map((mark) => asBlock(text, mark))) : null), [tokens, marks, text]);
  const inputs = useMemo(() => [...new Set(marks?.map((mark) => mark.name))], [marks]);
  const lines = text ? text.split("\n").length : 0;

  const content = useRef<HTMLPreElement>(null);
  const [height, setHeight] = useState(0);
  const [open, setOpen] = useState(false);
  useLayoutEffect(() => {
    const el = content.current;
    if (!el) return;
    const measure = () => setHeight(el.offsetHeight);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  // Folding only pays off when it hides a real chunk.
  const foldable = height > FOLDED + 72;

  return (
    <section className={cn("codeblock", className)} data-tone={tone}>
      <header className="codeblock-head">
        {icon && <span className="codeblock-icon">{icon}</span>}
        <span className="codeblock-title">{title}</span>
        {badge}
        <span className="codeblock-meta">
          {lines.toLocaleString()} {lines === 1 ? "line" : "lines"} · {text.length.toLocaleString()} chars
        </span>
        <CopyButton text={text} label="Copy" className="-mr-1 ml-auto" />
      </header>
      {inputs.length > 0 && (
        <div className="codeblock-legend">
          <span>Inputs</span>
          {inputs.map((name) => (
            <span key={name} className="codeblock-input-chip">
              {name}
            </span>
          ))}
        </div>
      )}
      <div
        className="codeblock-body"
        data-folded={foldable && !open ? "" : undefined}
        style={foldable ? { maxHeight: open ? height : FOLDED } : undefined}
      >
        <pre ref={content} className="codeblock-pre">
          {!text ? (
            <span className="text-faint">empty</span>
          ) : parts ? (
            parts.map((part, i) =>
              part.mark ? (
                <mark
                  key={i}
                  className="codeblock-input"
                  data-var={part.mark.name}
                  data-block={part.mark.block ? "" : undefined}
                  title={`{{${part.mark.name}}}`}
                >
                  <Tokens tokens={part.tokens} />
                </mark>
              ) : (
                <Tokens key={i} tokens={part.tokens} />
              ),
            )
          ) : (
            <Tokens tokens={tokens} />
          )}
        </pre>
      </div>
      {foldable && (
        <button
          type="button"
          className="codeblock-toggle"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          {...cues.press}
        >
          <ChevronDown />
          {open ? "Show less" : `Show all ${lines.toLocaleString()} lines`}
        </button>
      )}
    </section>
  );
}

/** An input that fills whole lines renders as a full-width band rather than a ragged
 *  inline highlight. The band takes the newline after it, which its own box ends. */
function asBlock(text: string, mark: Mark): Mark & { block?: boolean } {
  const ownLines =
    (mark.start === 0 || text[mark.start - 1] === "\n") &&
    (mark.end === text.length || text[mark.end] === "\n") &&
    text.slice(mark.start, mark.end).includes("\n");
  if (!ownLines) return mark;
  return { ...mark, end: mark.end < text.length ? mark.end + 1 : mark.end, block: true };
}

function Tokens({ tokens }: { tokens: Token[] }) {
  return tokens.map((token, i) =>
    token.kind ? (
      <span key={i} className={`tk-${token.kind}`}>
        {token.text}
      </span>
    ) : (
      <Fragment key={i}>{token.text}</Fragment>
    ),
  );
}
