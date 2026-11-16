/** A small, dependency-free highlighter for LLM payloads. Prompts mix prose, light
 *  markdown, {{placeholders}}, fenced blocks and inline JSON in one string, which a
 *  single-language grammar can't color, so this reads each region on its own terms. */

export type TokenKind =
  | "key"
  | "string"
  | "number"
  | "literal"
  | "punct"
  | "heading"
  | "marker"
  | "code"
  | "strong"
  | "tag"
  | "var"
  | "fence";
export type Token = { text: string; kind?: TokenKind };
/** A span of rendered text that came from a template variable. */
export type Mark = { start: number; end: number; name: string };

/** Past this size, show plain text: highlighting would cost more than it gives. */
const LIMIT = 200_000;
const NAME = "[a-z][a-z0-9_]{0,59}";
const PLACEHOLDER = new RegExp(`\\{\\{\\s*(${NAME})\\s*\\}\\}`);

export function highlight(text: string): Token[] {
  if (!text) return [];
  if (text.length > LIMIT) return [{ text }];
  const out: Token[] = [];
  let prose = 0;
  let i = 0;
  const flush = (end: number) => {
    if (end > prose) proseTokens(text.slice(prose, end), prose === 0 || text[prose - 1] === "\n", out);
  };
  while (i < text.length) {
    const ch = text[i];
    let end = -1;
    if (ch === "`" && (i === 0 || text[i - 1] === "\n")) end = fenceEnd(text, i);
    else if (ch === "{" || ch === "[") end = jsonEnd(text, i);
    if (end > 0) {
      flush(i);
      if (ch === "`") fenceTokens(text.slice(i, end), out);
      else jsonTokens(text.slice(i, end), out);
      i = prose = end;
    } else i++;
  }
  flush(text.length);
  return merge(out);
}

/** The whole text pretty-printed, when it is a JSON object or array; otherwise null. */
export function formatJson(text: string | null | undefined): string | null {
  const trimmed = text?.trim();
  if (!trimmed || !/^[{[]/.test(trimmed)) return null;
  try {
    return JSON.stringify(JSON.parse(trimmed), null, 2);
  } catch {
    return null;
  }
}

/**
 * Where each {{variable}} landed in `rendered`, found by matching the text against the
 * template it was rendered from. Returns [] when the text doesn't fit the template.
 */
export function locateInputs(template: string, rendered: string): Mark[] {
  const parts = template.split(PLACEHOLDER);
  const groups = (parts.length - 1) / 2;
  if (!groups || groups > 24 || rendered.length > LIMIT) return [];
  // Cheap necessary checks first, so a mismatch never reaches the backtracking regex.
  const literals = parts.filter((_, i) => i % 2 === 0);
  if (!rendered.startsWith(literals[0]) || !rendered.endsWith(literals[literals.length - 1])) return [];
  let at = 0;
  for (const literal of literals) {
    const found = rendered.indexOf(literal, at);
    if (found < 0) return [];
    at = found + literal.length;
  }
  const seen = new Set<string>();
  const names: string[] = [];
  let source = "^";
  parts.forEach((part, i) => {
    if (i % 2 === 0) {
      source += part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      return;
    }
    names.push(part);
    // A variable used twice rendered the same text twice.
    source += seen.has(part) ? `(\\k<${part}>)` : `(?<${part}>[\\s\\S]*?)`;
    seen.add(part);
  });
  const match = new RegExp(`${source}$`, "d").exec(rendered);
  const indices = match?.indices;
  if (!indices) return [];
  const marks: Mark[] = [];
  names.forEach((name, i) => {
    const span = indices[i + 1];
    if (span && span[1] > span[0]) marks.push({ start: span[0], end: span[1], name });
  });
  return marks;
}

/** Splits tokens at mark boundaries: runs of tokens, each inside one mark or none. */
export function segment<M extends Mark>(tokens: Token[], marks: M[]): { mark?: M; tokens: Token[] }[] {
  const bounds: { end: number; mark?: M }[] = [];
  let at = 0;
  for (const mark of [...marks].sort((a, b) => a.start - b.start)) {
    if (mark.start < at) continue;
    if (mark.start > at) bounds.push({ end: mark.start });
    bounds.push({ end: mark.end, mark });
    at = mark.end;
  }
  bounds.push({ end: Infinity });
  const out: { mark?: M; tokens: Token[] }[] = [];
  let b = 0;
  let pos = 0;
  let current = { mark: bounds[0].mark, tokens: [] as Token[] };
  out.push(current);
  for (const token of tokens) {
    let offset = 0;
    while (offset < token.text.length) {
      const take = Math.min(token.text.length - offset, bounds[b].end - pos);
      current.tokens.push({ text: token.text.slice(offset, offset + take), kind: token.kind });
      offset += take;
      pos += take;
      if (pos >= bounds[b].end) {
        b++;
        current = { mark: bounds[b].mark, tokens: [] };
        out.push(current);
      }
    }
  }
  return out.filter((part) => part.tokens.length);
}

// ── regions ─────────────────────────────────────────────────────────────────

const FENCE_OPEN = /^```[\w+-]*[ \t]*\n/;

/** End of a ``` fenced block opening at `start`, or -1. */
function fenceEnd(text: string, start: number): number {
  const open = FENCE_OPEN.exec(text.slice(start, start + 64));
  if (!open) return -1;
  const close = text.indexOf("\n```", start + open[0].length - 1);
  return close < 0 ? -1 : close + 4;
}

/** End of a JSON object/array opening at `start`, or -1. Needs a string inside, so
 *  prose like `[1]` or `{}` stays prose. */
function jsonEnd(text: string, start: number): number {
  const closers: string[] = [];
  let inString = false;
  let quoted = false;
  for (let j = start; j < text.length; j++) {
    const c = text[j];
    if (inString) {
      if (c === "\\") j++;
      else if (c === '"') inString = false;
      else if (c === "\n") return -1;
      continue;
    }
    if (c === '"') inString = quoted = true;
    else if (c === "{") closers.push("}");
    else if (c === "[") closers.push("]");
    else if (c === "}" || c === "]") {
      if (closers.pop() !== c) return -1;
      if (closers.length) continue;
      if (!quoted) return -1;
      try {
        JSON.parse(text.slice(start, j + 1));
        return j + 1;
      } catch {
        return -1;
      }
    }
  }
  return -1;
}

// ── tokenizers ──────────────────────────────────────────────────────────────

const JSON_TOKEN = /("(?:[^"\\\n]|\\.)*")(\s*:)?|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false|null)\b|([{}[\],:])/g;

function jsonTokens(src: string, out: Token[]) {
  let last = 0;
  for (const m of src.matchAll(JSON_TOKEN)) {
    if (m.index > last) out.push({ text: src.slice(last, m.index) });
    if (m[1] && m[2]) out.push({ text: m[1], kind: "key" }, { text: m[2], kind: "punct" });
    else if (m[1]) out.push({ text: m[1], kind: "string" });
    else if (m[3]) out.push({ text: m[3], kind: "number" });
    else if (m[4]) out.push({ text: m[4], kind: "literal" });
    else out.push({ text: m[0], kind: "punct" });
    last = m.index + m[0].length;
  }
  if (last < src.length) out.push({ text: src.slice(last) });
}

function fenceTokens(block: string, out: Token[]) {
  const newline = block.indexOf("\n");
  const head = block.slice(0, newline + 1);
  const body = block.slice(newline + 1, -3);
  out.push({ text: head, kind: "fence" });
  if (head.slice(3).trim().toLowerCase() === "json" || formatJson(body) !== null) jsonTokens(body, out);
  else out.push({ text: body });
  out.push({ text: "```", kind: "fence" });
}

/** `# Heading` or a short label line such as `Rules:`. */
const HEADING = /^(?:#{1,6}\s.*|[A-Z][^\n:]{0,48}:[ \t]*)$/;
const LIST = /^([ \t]*)([-*•]|\d{1,3}[.)])(?=[ \t])/;
const INLINE = new RegExp(
  `(\\{\\{\\s*${NAME}\\s*\\}\\})|(\`[^\`\\n]+\`)|(\\*\\*[^*\\n]+\\*\\*)|(<\\/?[A-Za-z][\\w-]*(?:\\s[^<>\\n]*)?\\/?>)`,
  "g",
);

function proseTokens(src: string, atLineStart: boolean, out: Token[]) {
  src.split("\n").forEach((line, index) => {
    if (index > 0) out.push({ text: "\n" });
    const lineStart = index > 0 || atLineStart;
    if (lineStart && HEADING.test(line)) return inline(line, out, "heading");
    const list = lineStart ? LIST.exec(line) : null;
    if (list) out.push({ text: list[1] }, { text: list[2], kind: "marker" });
    inline(list ? line.slice(list[0].length) : line, out);
  });
}

function inline(src: string, out: Token[], base?: TokenKind) {
  let last = 0;
  for (const m of src.matchAll(INLINE)) {
    if (m.index > last) out.push({ text: src.slice(last, m.index), kind: base });
    out.push({ text: m[0], kind: m[1] ? "var" : m[2] ? "code" : m[3] ? "strong" : "tag" });
    last = m.index + m[0].length;
  }
  if (last < src.length) out.push({ text: src.slice(last), kind: base });
}

function merge(tokens: Token[]): Token[] {
  const out: Token[] = [];
  for (const token of tokens) {
    if (!token.text) continue;
    const prev = out[out.length - 1];
    if (prev && prev.kind === token.kind) prev.text += token.text;
    else out.push({ ...token });
  }
  return out;
}
