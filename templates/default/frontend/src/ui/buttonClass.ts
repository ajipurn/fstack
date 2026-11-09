import { cn } from "./cn";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "soft" | "danger" | "danger-soft";
export type ButtonSize = "xs" | "sm" | "md" | "lg";

/** Class list for anything that should look like a button (e.g. a router <Link>). */
export function buttonClass({
  variant = "secondary",
  size = "md",
  icon,
  block,
  className,
}: {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: boolean;
  block?: boolean;
  className?: string;
}) {
  return cn(
    "btn",
    `btn-${variant}`,
    size !== "md" && `btn-${size}`,
    icon && "btn-icon",
    block && "btn-block",
    className,
  );
}
