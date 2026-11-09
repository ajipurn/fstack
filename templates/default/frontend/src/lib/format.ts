const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const whole = new Intl.NumberFormat("en-US");

export function usd(value: number | null | undefined, opts: { precise?: boolean } = {}): string {
  if (value === null || value === undefined) return "—";
  if (value === 0) return "$0.00";
  const abs = Math.abs(value);
  const digits = opts.precise ? (abs < 0.01 ? 5 : 4) : abs < 0.01 ? 4 : 2;
  return `$${value.toFixed(digits)}`;
}

export function tokens(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value >= 10_000 ? compact.format(value) : whole.format(value);
}

export function count(value: number): string {
  return whole.format(value);
}

export function ms(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value >= 1000 ? `${(value / 1000).toFixed(value >= 10_000 ? 0 : 1)}s` : `${Math.round(value)}ms`;
}

export function percent(value: number): string {
  return `${(value * 100).toFixed(value > 0 && value < 0.1 ? 1 : 0)}%`;
}

/** USD per 1M tokens, the unit models.dev publishes. */
export function perMillion(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `$${value < 1 ? value.toFixed(3).replace(/0+$/, "").replace(/\.$/, ".0") : value.toFixed(2)}`;
}

const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 31_557_600],
  ["month", 2_629_800],
  ["week", 604_800],
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
  ["second", 1],
];

export function ago(iso: string | null | undefined): string {
  if (!iso) return "never";
  const seconds = (new Date(iso).getTime() - Date.now()) / 1000;
  if (Math.abs(seconds) < 10) return "just now";
  const [unit, size] = UNITS.find(([, size]) => Math.abs(seconds) >= size) ?? UNITS[UNITS.length - 1];
  return rtf.format(Math.round(seconds / size), unit);
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));
}

export function shortDay(day: string): string {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(`${day}T00:00:00Z`));
}
