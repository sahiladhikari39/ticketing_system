/**
 * ONE consistent date format everywhere in the app, regardless of who's
 * looking at it or what machine they're on.
 *
 * `.toLocaleDateString()` on its own renders differently depending on
 * the VIEWER's own browser/OS locale settings -- 7/23/2026 for someone
 * on a US-locale machine, 23/07/2026 for almost everyone else, and
 * other orderings entirely depending on the exact locale. That's not
 * a "global standard" -- it's whatever each individual person's
 * machine happens to be configured for, which is exactly the kind of
 * inconsistency a real client would (rightly) flag.
 *
 * These two functions always render the same way for everyone:
 * YYYY-MM-DD for a date, YYYY-MM-DD HH:MM (24-hour clock) for a full
 * timestamp -- matching the backend's own ISO 8601 format, which is
 * already correct (confirmed directly against the API).
 */

export function formatDate(dateInput) {
  if (!dateInput) return "—";
  const d = new Date(dateInput);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function formatDateTime(dateInput) {
  if (!dateInput) return "—";
  const d = new Date(dateInput);
  const hours = String(d.getHours()).padStart(2, "0");
  const minutes = String(d.getMinutes()).padStart(2, "0");
  return `${formatDate(d)} ${hours}:${minutes}`;
}
