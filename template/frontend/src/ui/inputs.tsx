import { Combobox as BaseCombobox } from "@base-ui/react/combobox";
import { Select as BaseSelect } from "@base-ui/react/select";
import { Switch as BaseSwitch } from "@base-ui/react/switch";
import { Check, ChevronDown } from "@gravity-ui/icons";
import type { ComponentProps, ReactNode } from "react";
import { cues } from "../lib/sound";
import { cn } from "./cn";
import { ScrollArea } from "./ScrollArea";

// React 19: `ref` is a regular prop, so these stay plain functions.
export function Input({ className, invalid, ...props }: ComponentProps<"input"> & { invalid?: boolean }) {
  return <input className={cn("control", className)} aria-invalid={invalid || undefined} {...props} />;
}

export function Textarea({ className, invalid, ...props }: ComponentProps<"textarea"> & { invalid?: boolean }) {
  return <textarea className={cn("control", className)} aria-invalid={invalid || undefined} {...props} />;
}

export type Option<V extends string = string> = {
  value: V;
  label: ReactNode;
  description?: ReactNode;
  disabled?: boolean;
};

export function Select<V extends string = string>({
  value,
  onChange,
  options,
  placeholder = "Select…",
  disabled,
  size,
  className,
  id,
  "aria-label": ariaLabel,
}: {
  value: V | "" | null;
  onChange: (value: V) => void;
  options: Option<V>[];
  placeholder?: string;
  disabled?: boolean;
  size?: "sm";
  className?: string;
  id?: string;
  "aria-label"?: string;
}) {
  const items = options.map((o) => ({ value: o.value, label: o.label }));
  return (
    <BaseSelect.Root
      items={items}
      value={value || null}
      disabled={disabled}
      onValueChange={(next) => {
        if (typeof next === "string") onChange(next as V);
      }}
    >
      <BaseSelect.Trigger
        id={id}
        aria-label={ariaLabel}
        className={cn("control justify-between text-left", size === "sm" && "control-sm", className)}
        {...cues.press}
      >
        <BaseSelect.Value placeholder={placeholder} className="min-w-0 flex-1 truncate data-[placeholder]:text-faint" />
        <BaseSelect.Icon className="shrink-0 text-muted [&_svg]:size-3.5">
          <ChevronDown />
        </BaseSelect.Icon>
      </BaseSelect.Trigger>
      <BaseSelect.Portal>
        <BaseSelect.Positioner alignItemWithTrigger={false} sideOffset={6} className="z-[90]">
          <BaseSelect.Popup className="popup w-[var(--anchor-width)] min-w-[12rem]">
            <ScrollArea className="max-h-[min(20rem,var(--available-height))]">
              <BaseSelect.List>
                {options.map((option) => (
                  <BaseSelect.Item
                    key={option.value}
                    value={option.value}
                    disabled={option.disabled}
                    className="menu-item justify-between"
                    {...cues.hover}
                  >
                    <span className="min-w-0">
                      <BaseSelect.ItemText className="block truncate">{option.label}</BaseSelect.ItemText>
                      {option.description && (
                        <span className="block truncate text-xs text-muted">{option.description}</span>
                      )}
                    </span>
                    <BaseSelect.ItemIndicator className="shrink-0 text-ink [&_svg]:size-3.5">
                      <Check />
                    </BaseSelect.ItemIndicator>
                  </BaseSelect.Item>
                ))}
              </BaseSelect.List>
            </ScrollArea>
          </BaseSelect.Popup>
        </BaseSelect.Positioner>
      </BaseSelect.Portal>
    </BaseSelect.Root>
  );
}

/** Searchable pick from a provider's model list (often hundreds). When the provider
 * listed nothing, a plain field so a model id can still be typed. */
export function ModelPicker({
  models,
  value,
  onChange,
  disabled,
  id,
  "aria-label": ariaLabel,
}: {
  models: string[];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  id?: string;
  "aria-label"?: string;
}) {
  if (!models.length) {
    return (
      <Input
        id={id}
        aria-label={ariaLabel}
        className="mono"
        value={value}
        disabled={disabled}
        placeholder="model id"
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  // Keep a bound model visible even if the provider stopped listing it.
  const items = value && !models.includes(value) ? [value, ...models] : models;
  return (
    <BaseCombobox.Root
      items={items}
      value={value || null}
      disabled={disabled}
      limit={200}
      onValueChange={(next) => {
        if (typeof next === "string") onChange(next);
      }}
    >
      <div className="relative">
        <BaseCombobox.Input id={id} aria-label={ariaLabel} placeholder="Search models…" className="control mono pr-8" />
        <BaseCombobox.Trigger
          aria-label="Show models"
          className="absolute inset-y-0 right-0 flex w-8 items-center justify-center text-muted [&_svg]:size-3.5"
        >
          <ChevronDown />
        </BaseCombobox.Trigger>
      </div>
      <BaseCombobox.Portal>
        <BaseCombobox.Positioner sideOffset={6} className="z-[90]">
          <BaseCombobox.Popup className="popup w-[var(--anchor-width)] min-w-[12rem]">
            <BaseCombobox.Empty className="px-3 py-2 text-xs text-muted empty:hidden">No matching model</BaseCombobox.Empty>
            <ScrollArea className="max-h-[min(20rem,var(--available-height))]">
              <BaseCombobox.List>
                {(item: string) => (
                  <BaseCombobox.Item key={item} value={item} className="menu-item justify-between" {...cues.hover}>
                    <span className="mono min-w-0 truncate text-xs">{item}</span>
                    <BaseCombobox.ItemIndicator className="shrink-0 text-ink [&_svg]:size-3.5">
                      <Check />
                    </BaseCombobox.ItemIndicator>
                  </BaseCombobox.Item>
                )}
              </BaseCombobox.List>
            </ScrollArea>
          </BaseCombobox.Popup>
        </BaseCombobox.Positioner>
      </BaseCombobox.Portal>
    </BaseCombobox.Root>
  );
}

export function Switch({
  checked,
  onChange,
  disabled,
  "aria-label": ariaLabel,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  "aria-label"?: string;
}) {
  return (
    <BaseSwitch.Root
      checked={checked}
      onCheckedChange={onChange}
      disabled={disabled}
      aria-label={ariaLabel}
      className="switch"
      {...cues.toggle}
    >
      <BaseSwitch.Thumb className="switch-thumb" />
    </BaseSwitch.Root>
  );
}

export function Segmented<V extends string>({
  value,
  onChange,
  options,
  "aria-label": ariaLabel,
}: {
  value: V;
  onChange: (value: V) => void;
  options: { value: V; label: ReactNode }[];
  "aria-label"?: string;
}) {
  return (
    <div className="segmented" role="group" aria-label={ariaLabel}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className="segmented-item"
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
          {...cues.toggle}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
