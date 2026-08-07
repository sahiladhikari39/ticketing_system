/**
 * Plain-language labels for the coded values the API returns.
 *
 * Deliberately text, not coloured pills. Pills read as decoration in a
 * dense operational table and, worse, they duplicated information that
 * was already on screen -- a ticket showed its status as a badge in the
 * header AND as the selected option in the dropdown right below it.
 * One clear written value beats two competing visual ones.
 */

const STATUS = {
  open: "Open",
  in_progress: "In progress",
  on_hold: "On hold",
  resolved: "Resolved",
  closed: "Closed",
};

const PRIORITY = {
  low: "Low",
  medium: "Medium",
  high: "High",
  urgent: "Urgent",
};

const ROLE = {
  soori_admin: "Platform Admin",
  client_admin: "Service Manager",
  support_staff: "Service Team",
  sub_client: "Customer",
};

const titleise = (v) =>
  String(v || "").replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export const statusLabel = (v) => STATUS[v] || titleise(v);
export const priorityLabel = (v) => PRIORITY[v] || titleise(v);
export const roleLabel = (v) => ROLE[v] || titleise(v);
