import { describe, expect, it } from "vitest";
import { ms, perMillion, tokens, usd } from "./format";

describe("format", () => {
  it("prints small costs with enough precision", () => {
    expect(usd(0)).toBe("$0.00");
    expect(usd(1.234)).toBe("$1.23");
    expect(usd(0.00412)).toBe("$0.0041");
    expect(usd(0.00412, { precise: true })).toBe("$0.00412");
    expect(usd(null)).toBe("—");
  });

  it("compacts large token counts", () => {
    expect(tokens(9_999)).toBe("9,999");
    expect(tokens(1_250_000)).toBe("1.3M");
  });

  it("formats latency and per-million prices", () => {
    expect(ms(820)).toBe("820ms");
    expect(ms(2300)).toBe("2.3s");
    expect(perMillion(0.075)).toBe("$0.075");
    expect(perMillion(15)).toBe("$15.00");
  });
});
