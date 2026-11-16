import { describe, expect, it } from "vitest";
import { formatJson, highlight, locateInputs, segment, type Token } from "./highlight";

const kinds = (tokens: Token[]) => tokens.filter((t) => t.kind).map((t) => [t.kind, t.text]);
const text = (tokens: Token[]) => tokens.map((t) => t.text).join("");

describe("highlight", () => {
  it("keeps the text intact", () => {
    const src = 'Rules:\n1. Use `OBSERVED` for {{name}}.\n{"a": [1, true, null]}\n```json\n{"b": "c"}\n```';
    expect(text(highlight(src))).toBe(src);
  });

  it("colors JSON embedded in prose", () => {
    const tokens = highlight('Evaluation input:\n{\n  "id": "x",\n  "n": 2.5,\n  "ok": false\n}');
    expect(kinds(tokens)).toEqual(
      expect.arrayContaining([
        ["heading", "Evaluation input:"],
        ["key", '"id"'],
        ["string", '"x"'],
        ["number", "2.5"],
        ["literal", "false"],
      ]),
    );
  });

  it("marks prompt structure", () => {
    const tokens = highlight("## Task\n- read **all** of <doc>\n3. return `JSON` for {{ topic }}");
    expect(kinds(tokens)).toEqual([
      ["heading", "## Task"],
      ["marker", "-"],
      ["strong", "**all**"],
      ["tag", "<doc>"],
      ["marker", "3."],
      ["code", "`JSON`"],
      ["var", "{{ topic }}"],
    ]);
  });

  it("leaves bracketed prose alone", () => {
    expect(kinds(highlight("see [1] and {} or {{x"))).toEqual([]);
  });
});

describe("locateInputs", () => {
  it("finds where each variable landed", () => {
    const rendered = 'Text:\n{"a": 1}\n\nQuestion: why?';
    const marks = locateInputs("Text:\n{{text}}\n\nQuestion: {{ question }}", rendered);
    expect(marks.map((m) => [m.name, rendered.slice(m.start, m.end)])).toEqual([
      ["text", '{"a": 1}'],
      ["question", "why?"],
    ]);
  });

  it("handles a variable used twice", () => {
    const marks = locateInputs("{{a}} and {{a}}", "x y and x y");
    expect(marks).toEqual([
      { start: 0, end: 3, name: "a" },
      { start: 8, end: 11, name: "a" },
    ]);
  });

  it("gives up when the text doesn't fit the template", () => {
    expect(locateInputs("Hello {{name}}!", "Goodbye Ana!")).toEqual([]);
    expect(locateInputs("No variables", "No variables")).toEqual([]);
  });
});

describe("segment", () => {
  it("splits tokens at mark edges", () => {
    const parts = segment([{ text: "abc" }, { text: "def", kind: "key" }], [{ start: 2, end: 4, name: "v" }]);
    expect(parts).toEqual([
      { mark: undefined, tokens: [{ text: "ab", kind: undefined }] },
      {
        mark: { start: 2, end: 4, name: "v" },
        tokens: [
          { text: "c", kind: undefined },
          { text: "d", kind: "key" },
        ],
      },
      { mark: undefined, tokens: [{ text: "ef", kind: "key" }] },
    ]);
  });
});

describe("formatJson", () => {
  it("pretty-prints whole JSON documents only", () => {
    expect(formatJson('{"a":[1]}')).toBe('{\n  "a": [\n    1\n  ]\n}');
    expect(formatJson("Sure! {}")).toBeNull();
    expect(formatJson("{broken")).toBeNull();
  });
});
