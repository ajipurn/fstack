import { APP_NAME, monogram } from "./brand";

const LETTERS = monogram(APP_NAME);

/** The logo: the app's initials on its accent. The favicon draws the same mark.
 *  sm: header (24px) · md: sidebar (28px) · lg: sign-in (36px). */
export function BrandMark({ size = "sm" }: { size?: "sm" | "md" | "lg" }) {
  return (
    <span className="brand-mark" data-size={size} data-letters={LETTERS.length} aria-hidden="true">
      {LETTERS}
    </span>
  );
}
