/**
 * The app's identity. `fstack new` fills in the name; edit it freely. The logo
 * (BrandMark) and the favicon (vite.config.ts) are drawn from it, so they follow it.
 * No DOM or React here: vite.config.ts imports this file.
 */

export const APP_NAME = "Fstack Starter";

/** Up to two initials for the logo and the favicon: "Acme Console" → "AC", "crm" → "C". */
export function monogram(name: string): string {
  const words = name.match(/[\p{L}\p{N}]+/gu) ?? [];
  const initials = words.slice(0, 2).map((word) => Array.from(word)[0]);
  return initials.join("").toUpperCase() || "?";
}
