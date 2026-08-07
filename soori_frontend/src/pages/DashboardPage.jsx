import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ticketsApi, clientsApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { statusLabel, priorityLabel } from "../utils/labels";
import { formatDate } from "../utils/format";

const TERMINAL_STATUSES = ["resolved", "closed"];
// Confirmed gap: this used to include ANY support_staff, which meant a
// Field Engineer saw the company's subscription/billing status too --
// that's Service Layer information (Manager + Service Department),
// not something a Field Engineer needs or should see. Checked properly
// below, per-user, since "support_staff" alone doesn't distinguish the
// two tiers -- the permission does.

function daysPending(createdAt) {
  const created = new Date(createdAt);
  const today = new Date();
  const diffMs = today - created;
  return Math.max(0, Math.floor(diffMs / (1000 * 60 * 60 * 24)));
}

function daysRemainingLabel(days) {
  if (days === null || days === undefined) return "No end date set";
  if (days < 0) return `Expired ${Math.abs(days)}d ago`;
  if (days === 0) return "Expires today";
  return `${days} days remaining`;
}

function daysRemainingColor(days) {
  if (days === null || days === undefined) return "var(--ink-soft)";
  if (days < 0) return "var(--accent-urgent)";
  if (days <= 14) return "var(--accent-warn)";
  return "var(--accent-success)";
}

const PLAN_LABELS = { basic: "Basic", pro: "Pro", enterprise: "Enterprise" };

export default function DashboardPage() {
  const { user } = useAuth();
  const [tickets, setTickets] = useState(null);
  const [error, setError] = useState(null);
  const [subscription, setSubscription] = useState(null);
  const isCustomer = user.role === "sub_client";
  // A Field Engineer's queryset is already scoped to tickets assigned
  // to THEM specifically (see TicketViewSet.get_queryset on the
  // backend) -- so "Assigned to" would say their own name on every
  // single row, and "Updated" matters less to someone doing the work
  // than to whoever's triaging across engineers. Service Department
  // and the Manager assign across MULTIPLE engineers, so both columns
  // are genuinely useful information for them specifically.
  const canAssign = (user.staff_permissions || []).includes("tickets.assign") || user.role === "client_admin";
  const isPlainEngineer = !isCustomer && !canAssign;

  useEffect(() => {
    ticketsApi
      .list()
      .then(setTickets)
      .catch((err) => setError(err));
  }, [user.role]);

  useEffect(() => {
    const canSeeSubscription =
      user.role === "client_admin" || (user.staff_permissions || []).includes("service_report.approve");
    if (!canSeeSubscription) return;
    // /api/clients/ is already scoped to "just your own company" for
    // every non-Soori-Admin role (see ClientViewSet.get_queryset) --
    // no separate endpoint needed, this just reuses that existing
    // scoping for free.
    clientsApi
      .list()
      .then((clients) => setSubscription(clients[0] || null))
      .catch(() => setSubscription(null));
  }, [user.role]);

  // Counts derived entirely from what the server already sent -- no
  // extra request needed just to show these numbers.
  const openCount = tickets ? tickets.filter((t) => !TERMINAL_STATUSES.includes(t.status)).length : 0;
  const resolvedCount = tickets ? tickets.filter((t) => TERMINAL_STATUSES.includes(t.status)).length : 0;

  return (
    <>
      <div className="page-header">
        <div>
          <h1>{user.role === "sub_client" ? "My tickets" : "Tickets"}</h1>
          {/* This list is EXACTLY what the API returns for this role --
              no client-side filtering happens here. A Sub-Client only
              ever receives their own ticket from the server; a Soori
              Admin receives every ticket across every company. The
              frontend never has to reason about who should see what. */}
          <p>
            {user.role === "client_admin" && "All tickets for your organization."}
            {user.role === "support_staff" && "Your team's ticket queue."}
            {user.role === "sub_client" && "Every ticket you've raised, and where each one stands."}
          </p>
        </div>
        {user.role === "sub_client" && (
          <Link to="/new-ticket" className="btn btn-primary">
            + New ticket
          </Link>
        )}
      </div>

      {/*
        This is an expected business state (a lapsed subscription),
        not a bug -- shown as a calm, centered notice instead of the
        small red error banner used for genuine errors elsewhere.
        Detected via err.code (set server-side by
        IsClientSubscriptionActive), not by matching message text,
        so this keeps working even if the wording changes later.
      */}
      {error && error.code === "subscription_inactive" ? (
        <div className="card" style={{ padding: 40, textAlign: "center", maxWidth: 480, margin: "40px auto" }}>
          <h3 style={{ marginBottom: 8 }}>
            {user.role === "sub_client" ? "Temporarily unavailable" : "Subscription needed"}
          </h3>
          <p style={{ color: "var(--ink-soft)", margin: 0 }}>{error.message}</p>
        </div>
      ) : (
        <>
          {error && <div className="error-banner">{error.message}</div>}

          {subscription && (
            <div className="card" style={{ padding: 16, marginBottom: 24, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <div style={{ fontSize: "0.78rem", color: "var(--ink-soft)" }}>Your subscription</div>
                <div style={{ fontSize: "1rem", fontWeight: 600 }}>{PLAN_LABELS[subscription.plan] || subscription.plan} plan</div>
              </div>
              <div style={{ fontWeight: 700, color: daysRemainingColor(subscription.days_remaining) }}>
                {daysRemainingLabel(subscription.days_remaining)}
              </div>
            </div>
          )}

          {tickets && tickets.length > 0 && (
            <div style={{ display: "flex", gap: 16, marginBottom: 24 }}>
              <div className="card" style={{ padding: 16, flex: 1 }}>
                <div style={{ fontSize: "1.6rem", fontWeight: 700, color: "var(--primary)" }}>{openCount}</div>
                <div style={{ fontSize: "0.82rem", color: "var(--ink-soft)" }}>Open / pending</div>
              </div>
              <div className="card" style={{ padding: 16, flex: 1 }}>
                <div style={{ fontSize: "1.6rem", fontWeight: 700, color: "var(--accent-success)" }}>{resolvedCount}</div>
                <div style={{ fontSize: "0.82rem", color: "var(--ink-soft)" }}>Resolved / closed</div>
              </div>
            </div>
          )}

          {tickets === null && !error && <p>Loading tickets...</p>}

          {tickets && tickets.length === 0 && (
            <div className="empty-state card">
              <h3>No tickets yet</h3>
              <p>
                {user.role === "sub_client"
                  ? "Raise a ticket and it'll show up here."
                  : "Nothing's come in yet."}
              </p>
            </div>
          )}

          {tickets && tickets.length > 0 && (
            <div className="card" style={{ overflow: "hidden" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    {isCustomer ? (
                      <>
                        <th style={thStyle}>Date</th>
                        <th style={thStyle}>Title</th>
                        <th style={thStyle}>Status</th>
                        <th style={thStyle}>Service report</th>
                      </>
                    ) : (
                      <>
                        <th style={thStyle}>Title</th>
                        <th style={thStyle}>Status</th>
                        <th style={thStyle}>Priority</th>
                        <th style={thStyle}>Customer</th>
                        <th style={thStyle}>Location</th>
                        {!isPlainEngineer && <th style={thStyle}>Assigned to</th>}
                        <th style={thStyle}>Pending since</th>
                        {!isPlainEngineer && <th style={thStyle}>Updated</th>}
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {tickets.map((ticket) => {
                    const isPending = !TERMINAL_STATUSES.includes(ticket.status);
                    if (isCustomer) {
                      return (
                        <tr key={ticket.id} style={{ borderBottom: "1px solid var(--border)" }}>
                          <td style={tdStyle} className="mono">{formatDate(ticket.created_at)}</td>
                          <td style={tdStyle}>
                            <Link to={`/tickets/${ticket.id}`} style={{ fontWeight: 600, textDecoration: "none" }}>
                              {ticket.title}
                            </Link>
                          </td>
                          <td style={tdStyle}>{statusLabel(ticket.status)}</td>
                          <td style={tdStyle}>
                            {ticket.service_report_shared ? (
                              <Link to={`/tickets/${ticket.id}`} style={{ fontWeight: 600 }}>Read</Link>
                            ) : (
                              <span style={{ color: "var(--ink-soft)" }}>Not ready</span>
                            )}
                          </td>
                        </tr>
                      );
                    }
                    return (
                      <tr key={ticket.id} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td style={tdStyle}>
                          <Link to={`/tickets/${ticket.id}`} style={{ fontWeight: 600, textDecoration: "none" }}>
                            {ticket.title}
                          </Link>
                        </td>
                        <td style={tdStyle}>{statusLabel(ticket.status)}</td>
                        <td style={tdStyle}>{priorityLabel(ticket.priority)}</td>
                        <td style={tdStyle}>
                          {ticket.created_by_company}
                          <div style={{ fontSize: "0.78rem", color: "var(--ink-soft)" }}>
                            {ticket.created_by_username}
                          </div>
                        </td>
                        <td style={tdStyle}>
                          {/* Its own column, not stacked into the customer
                              cell -- visible across the whole queue so
                              Service Department can decide who to assign
                              by area without opening each ticket first. */}
                          {ticket.customer_service_area || "\u2014"}
                        </td>
                        {!isPlainEngineer && (
                          <td style={tdStyle}>
                            {ticket.assigned_to_username || (
                              <span style={{ color: "var(--accent-warn)" }}>Unassigned</span>
                            )}
                          </td>
                        )}
                        <td style={tdStyle} className="mono">
                          {isPending ? `${daysPending(ticket.created_at)}d` : "\u2014"}
                        </td>
                        {!isPlainEngineer && (
                          <td style={tdStyle} className="mono">{formatDate(ticket.updated_at)}</td>
                        )}
                      </tr>
                    );
                  })}
                  </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </>
  );
}

const thStyle = { padding: "12px 16px", fontSize: "0.8rem", color: "var(--ink-soft)", fontWeight: 600 };
const tdStyle = { padding: "12px 16px", fontSize: "0.92rem" };
