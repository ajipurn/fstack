import type { ComponentProps, ReactNode } from "react";
import { cues } from "../lib/sound";
import { buttonClass, type ButtonSize, type ButtonVariant } from "./buttonClass";
import { Spinner } from "./surfaces";

export type { ButtonSize, ButtonVariant };

export type ButtonProps = Omit<ComponentProps<"button">, "children"> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: boolean;
  block?: boolean;
  pending?: boolean;
  children?: ReactNode;
};

export function Button({
  variant = "secondary",
  size = "md",
  icon,
  block,
  pending,
  disabled,
  className,
  type = "button",
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      {...cues.press}
      {...props}
      type={type}
      disabled={disabled || pending}
      data-pending={pending ? "true" : undefined}
      className={buttonClass({ variant, size, icon, block, className })}
    >
      {pending ? <Spinner /> : null}
      {children}
    </button>
  );
}
