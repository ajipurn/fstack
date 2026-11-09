import type { ReactNode } from "react";
import { Morph } from "./Morph";
import { Skeleton } from "./surfaces";

/** KPI tile: label in the gray frame, morphing value on the white card. */
export function Stat({
  label,
  value,
  hint,
  loading,
}: {
  label: ReactNode;
  value: string;
  hint?: ReactNode;
  loading?: boolean;
}) {
  return (
    <div className="panel">
      <div className="panel-head">{label}</div>
      <div className="panel-body flex min-h-[4.5rem] flex-col justify-center gap-1.5 px-4 py-3.5">
        {loading ? <Skeleton className="h-6 w-24" /> : <Morph className="stat-value">{value}</Morph>}
        {hint && <div className="truncate text-xs text-muted">{hint}</div>}
      </div>
    </div>
  );
}
