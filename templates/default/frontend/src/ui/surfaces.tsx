import type { ComponentProps, ReactNode } from "react";
import { cn } from "./cn";

export function Panel({
  title,
  actions,
  footer,
  className,
  bodyClassName,
  children,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  footer?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}) {
  return (
    <section className={cn("panel", className)}>
      {(title || actions) && (
        <header className="panel-head">
          <div className="min-w-0 flex-1 truncate">{title}</div>
          {actions}
        </header>
      )}
      <div className={cn("panel-body", bodyClassName)}>{children}</div>
      {footer && <footer className="panel-foot">{footer}</footer>}
    </section>
  );
}

export function Card({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("card", className)} {...props} />;
}

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  eyebrow?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1.5 text-xs font-medium text-muted">{eyebrow}</div>}
        <h1 className="page-title">{title}</h1>
        {description && <p className="page-desc">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export type Tone = "neutral" | "ok" | "warn" | "danger" | "info" | "accent";

export function Chip({
  tone = "neutral",
  outline,
  className,
  children,
}: {
  tone?: Tone;
  outline?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span className={cn("chip", tone !== "neutral" && `chip-${tone}`, outline && "chip-outline", className)}>
      {children}
    </span>
  );
}

const DOT: Record<Tone, string> = {
  neutral: "text-faint",
  ok: "text-ok",
  warn: "text-warn",
  danger: "text-danger",
  info: "text-info",
  accent: "text-accent",
};

export function Dot({ tone = "neutral", pulse }: { tone?: Tone; pulse?: boolean }) {
  return <span className={cn("dot", DOT[tone])} data-pulse={pulse ? "" : undefined} aria-hidden="true" />;
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={cn("spin", className)} viewBox="0 0 16 16" width="14" height="14" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
      <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton", className)} />;
}

export function Empty({
  icon,
  title,
  children,
  action,
  className,
}: {
  icon?: ReactNode;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-14 text-center fade-up", className)}>
      {icon && (
        <div className="mb-4 grid size-10 place-items-center rounded-xl bg-surface-2 text-muted shadow-[inset_0_0_0_1px_var(--line)] [&_svg]:size-[18px]">
          {icon}
        </div>
      )}
      <div className="text-sm font-semibold text-ink">{title}</div>
      {children && <p className="mt-1 max-w-sm text-sm text-muted">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="kbd">{children}</kbd>;
}

export function Field({
  label,
  hint,
  error,
  htmlFor,
  className,
  children,
}: {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  htmlFor?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={className}>
      {label && (
        <label className="label" htmlFor={htmlFor}>
          {label}
        </label>
      )}
      {children}
      {error ? <p className="hint hint-error">{error}</p> : hint ? <p className="hint">{hint}</p> : null}
    </div>
  );
}
