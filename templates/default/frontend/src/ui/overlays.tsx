import { AlertDialog } from "@base-ui/react/alert-dialog";
import { Dialog as BaseDialog } from "@base-ui/react/dialog";
import { Menu as BaseMenu } from "@base-ui/react/menu";
import { Tooltip as BaseTooltip } from "@base-ui/react/tooltip";
import { Xmark } from "@gravity-ui/icons";
import type { CSSProperties, ReactElement, ReactNode } from "react";
import { Drawer as Vaul } from "vaul";
import { cues } from "../lib/sound";
import { Button } from "./Button";
import { cn } from "./cn";
import { ScrollArea } from "./ScrollArea";

// ── Dialog ──────────────────────────────────────────────────────────────────

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  footer,
  width = "32rem",
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  footer?: ReactNode;
  width?: string;
  children: ReactNode;
}) {
  return (
    <BaseDialog.Root open={open} onOpenChange={onOpenChange}>
      <BaseDialog.Portal>
        <BaseDialog.Backdrop className="dialog-backdrop" />
        <BaseDialog.Popup className="dialog-popup" style={{ "--dialog-w": width } as CSSProperties}>
          <div className="dialog-head flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <BaseDialog.Title className="dialog-title">{title}</BaseDialog.Title>
              {description && <BaseDialog.Description className="dialog-desc">{description}</BaseDialog.Description>}
            </div>
            <BaseDialog.Close className="btn btn-ghost btn-icon btn-sm -mr-1.5 -mt-1" aria-label="Close" {...cues.press}>
              <Xmark />
            </BaseDialog.Close>
          </div>
          <ScrollArea className="dialog-body">{children}</ScrollArea>
          {footer && <div className="dialog-foot">{footer}</div>}
        </BaseDialog.Popup>
      </BaseDialog.Portal>
    </BaseDialog.Root>
  );
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirm",
  destructive,
  pending,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  confirmLabel?: string;
  destructive?: boolean;
  pending?: boolean;
  onConfirm: () => void;
}) {
  return (
    <AlertDialog.Root open={open} onOpenChange={onOpenChange}>
      <AlertDialog.Portal>
        <AlertDialog.Backdrop className="dialog-backdrop" />
        <AlertDialog.Popup className="dialog-popup" style={{ "--dialog-w": "25rem" } as CSSProperties}>
          <div className="dialog-head pb-5">
            <AlertDialog.Title className="dialog-title">{title}</AlertDialog.Title>
            {description && <AlertDialog.Description className="dialog-desc">{description}</AlertDialog.Description>}
          </div>
          <div className="dialog-foot">
            <AlertDialog.Close className="btn btn-secondary" {...cues.press}>
              Cancel
            </AlertDialog.Close>
            <Button variant={destructive ? "danger" : "primary"} pending={pending} onClick={onConfirm}>
              {confirmLabel}
            </Button>
          </div>
        </AlertDialog.Popup>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}

// ── Drawer (vaul) ───────────────────────────────────────────────────────────

export function Drawer({
  open,
  onOpenChange,
  title,
  description,
  actions,
  width = "30rem",
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  width?: string;
  children: ReactNode;
}) {
  return (
    <Vaul.Root open={open} onOpenChange={onOpenChange} direction="right">
      <Vaul.Portal>
        <Vaul.Overlay className="drawer-overlay" />
        <Vaul.Content className="drawer-content" style={{ "--drawer-w": width } as CSSProperties}>
          <div className="flex items-start gap-3 px-5 pb-3 pt-4 shadow-[inset_0_-1px_0_var(--line)]">
            <div className="min-w-0 flex-1">
              <Vaul.Title className="dialog-title truncate">{title}</Vaul.Title>
              <Vaul.Description className={cn("dialog-desc", !description && "sr-only")}>
                {description ?? "Details"}
              </Vaul.Description>
            </div>
            {actions}
            <Vaul.Close className="btn btn-ghost btn-icon btn-sm -mr-1.5" aria-label="Close" {...cues.press}>
              <Xmark />
            </Vaul.Close>
          </div>
          <ScrollArea className="min-h-0 flex-1">
            <div className="px-5 py-4">{children}</div>
          </ScrollArea>
        </Vaul.Content>
      </Vaul.Portal>
    </Vaul.Root>
  );
}

// ── Menu ────────────────────────────────────────────────────────────────────

export type MenuEntry =
  | { label: ReactNode; icon?: ReactNode; onSelect: () => void; danger?: boolean; disabled?: boolean; hint?: ReactNode }
  | { separator: true }
  | { heading: ReactNode };

export function Menu({
  trigger,
  items,
  align = "end",
  side = "bottom",
  header,
}: {
  trigger: ReactElement;
  items: MenuEntry[];
  align?: "start" | "center" | "end";
  side?: "top" | "bottom" | "left" | "right";
  header?: ReactNode;
}) {
  return (
    <BaseMenu.Root>
      <BaseMenu.Trigger render={trigger} />
      <BaseMenu.Portal>
        <BaseMenu.Positioner sideOffset={6} side={side} align={align} className="z-[70]">
          <BaseMenu.Popup className="popup min-w-[13rem]">
            {header}
            {items.map((item, index) => {
              if ("separator" in item) return <BaseMenu.Separator key={index} className="menu-sep" />;
              if ("heading" in item)
                return (
                  <div key={index} className="menu-label">
                    {item.heading}
                  </div>
                );
              return (
                <BaseMenu.Item
                  key={index}
                  className={cn("menu-item", item.danger && "menu-item-danger")}
                  disabled={item.disabled}
                  onClick={item.onSelect}
                  {...cues.hover}
                >
                  {item.icon}
                  <span className="flex-1">{item.label}</span>
                  {item.hint}
                </BaseMenu.Item>
              );
            })}
          </BaseMenu.Popup>
        </BaseMenu.Positioner>
      </BaseMenu.Portal>
    </BaseMenu.Root>
  );
}

// ── Tooltip ─────────────────────────────────────────────────────────────────

export function TooltipProvider({ children }: { children: ReactNode }) {
  return (
    <BaseTooltip.Provider delay={350} closeDelay={60}>
      {children}
    </BaseTooltip.Provider>
  );
}

export function Tooltip({
  content,
  side = "top",
  children,
}: {
  content: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  children: ReactElement;
}) {
  return (
    <BaseTooltip.Root>
      <BaseTooltip.Trigger render={children} />
      <BaseTooltip.Portal>
        <BaseTooltip.Positioner side={side} sideOffset={6} className="z-[80]">
          <BaseTooltip.Popup className="tooltip">{content}</BaseTooltip.Popup>
        </BaseTooltip.Positioner>
      </BaseTooltip.Portal>
    </BaseTooltip.Root>
  );
}
