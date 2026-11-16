/** Copies text, falling back to execCommand where the async Clipboard API is missing
 *  (plain-http deployments are not a secure context). */
export async function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Permission denied or document not focused: try the fallback.
    }
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  Object.assign(area.style, { position: "fixed", top: "0", left: "0", opacity: "0", pointerEvents: "none" });
  // Inside a modal, focus traps refuse focus outside the dialog: mount it there.
  const host = document.activeElement?.closest("[role='dialog']") ?? document.body;
  host.appendChild(area);
  area.select();
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    area.remove();
  }
}
