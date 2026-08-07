const STATUS_LABELS = {
  open: "Open",
  in_progress: "In progress",
  on_hold: "On hold",
  resolved: "Resolved",
  closed: "Closed",
};

const PRIORITY_LABELS = {
  low: "Low",
  medium: "Medium",
  high: "High",
  urgent: "Urgent",
};

export function StatusBadge({ status }) {
  return (
    <span className={`badge badge-status-${status}`}>
      {STATUS_LABELS[status] || status}
    </span>
  );
}

export function PriorityBadge({ priority }) {
  return (
    <span className={`badge badge-priority-${priority}`}>
      {PRIORITY_LABELS[priority] || priority}
    </span>
  );
}

const ROLE_LABELS = {
  soori_admin: "Soori Admin",
  client_admin: "Client Admin",
  support_staff: "Support Staff",
  sub_client: "Sub-Client",
};

export function RoleBadge({ role }) {
  return <span className="badge badge-role">{ROLE_LABELS[role] || role}</span>;
}
