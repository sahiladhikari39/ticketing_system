/**
 * Client-side size check, so a too-large file is caught the instant
 * it's chosen instead of after a failed upload. The backend enforces
 * the real limit regardless -- this is purely about not making
 * someone wait for a round trip to learn what they could know
 * immediately.
 */
export function formatBytes(bytes) {
  const mb = bytes / (1024 * 1024);
  if (mb >= 1024) return `${(mb / 1024).toFixed(2)}GB`;
  if (mb >= 1) return `${mb.toFixed(1)}MB`;
  return `${Math.max(1, Math.round(bytes / 1024))}KB`;
}

/** Returns null when the file is fine, or a readable error string. */
export function validateFileSize(file, maxBytes, kind = "File") {
  if (!file) return null;
  if (file.size > maxBytes) {
    return `${kind}s must be under ${formatBytes(maxBytes)} (this one is ${formatBytes(file.size)}).`;
  }
  return null;
}
