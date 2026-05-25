"use client";

export async function copyTextToClipboard(value: string): Promise<boolean> {
  if (!value) {
    return false;
  }

  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      // fall back below
    }
  }

  const input = document.createElement("textarea");
  input.value = value;
  input.setAttribute("readonly", "");
  input.style.position = "fixed";
  input.style.opacity = "0";
  document.body.appendChild(input);
  input.select();
  const success = document.execCommand("copy");
  document.body.removeChild(input);
  return success;
}

/** M5.4 — Copy an image URL to the clipboard using ClipboardItem API */
export async function copyImageToClipboard(imgSrc: string): Promise<boolean> {
  try {
    const response = await fetch(imgSrc, { credentials: "include" });
    if (!response.ok) return false;
    const blob = await response.blob();
    const mimeType = blob.type || "image/png";
    if (typeof ClipboardItem !== "undefined" && navigator.clipboard?.write) {
      const item = new ClipboardItem({ [mimeType]: blob });
      await navigator.clipboard.write([item]);
      return true;
    }
  } catch {
    // ClipboardItem not supported (Firefox) — fall through
  }
  return false;
}
