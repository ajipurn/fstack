import { TextMorph } from "torph/react";
import type { ElementType } from "react";
import { cn } from "./cn";

/** Text that morphs between values (torph). Numbers morph by place value. */
export function Morph({
  children,
  className,
  as = "span",
}: {
  children: string | number;
  className?: string;
  as?: ElementType;
}) {
  return (
    <TextMorph as={as} className={cn("morph", className)} locale="en-US" duration={380} respectReducedMotion>
      {children}
    </TextMorph>
  );
}
