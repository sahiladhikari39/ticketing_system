import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { ticketsApi, commentsApi, supportStaffApi, serviceReportsApi } from "../api/endpoints";
import ServiceReportPanel from "../components/ServiceReportPanel";
import HistoryAccessRequestPanel from "../components/HistoryAccessRequestPanel";
import { useAuth } from "../context/AuthContext";
import { statusLabel, priorityLabel } from "../utils/labels";
import { formatDateTime } from "../utils/format";

const STAFF_ROLES = ["support_staff", "client_admin", "soori_admin"];
const STATUS_LABELS = { open: "Open", in_progress: "In progress", on_hold: "On hold", resolved: "Resolved", closed: "Closed" };

export default function TicketDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [ticket, setTicket] = useState(null);
  const [staff, setStaff] = useState([]);
  const [error, setError] = useState(null);
  const [commentBody, setCommentBody] = useState("");
  const [isInternal, setIsInternal] = useState(false);
  const [posting, setPosting] = useState(false);

  const canManage = STAFF_ROLES.includes(user.role);
  // Mirrors the backend rule in TicketSerializer.validate(): deciding
  // WHO handles a ticket takes authority, unlike changing its status.
  // Showing this control to someone the server will reject would just
  // produce a confusing error, so it's hidden for them instead.
  const [canReassign, setCanReassign] = useState(false);
  const [customerArea, setCustomerArea] = useState("");
  const [assignConfirmation, setAssignConfirmation] = useState(null);
  const [report, setReport] = useState(null);
  const [reportLoaded, setReportLoaded] = useState(false);

  const loadTicket = useCallback(() => {
    ticketsApi.get(id).then(setTicket).catch((err) => setError(err.message));
    // Reports are a separate endpoint, and "no report yet" is a normal
    // state rather than an error -- so a failure here just means none
    // exists (or this role can't see it), not that the page is broken.
    serviceReportsApi
      .list()
      .then((all) => setReport(all.find((r) => r.ticket === id) || null))
      .catch(() => setReport(null))
      .finally(() => setReportLoaded(true));
  }, [id]);

  useEffect(() => {
    loadTicket();
    if (canManage) {
      // A Service Manager always qualifies -- set that up front rather
      // than depending on the roster fetch succeeding, since they
      // don't appear in the staff list at all.
      if (user.role === "client_admin") setCanReassign(true);
      supportStaffApi
        .list()
        .then((list) => {
          const me = list.find((s) => s.user === user.id);
          if (me?.staff_role === "service_department") setCanReassign(true);
        })
        .catch(() => {});
      // Engineers come from the ticket-specific endpoint rather than
      // the general roster, because it's the only thing that knows
      // which of them actually covers this customer's area.
      ticketsApi
        .nearbyEngineers(id)
        .then((data) => {
          setStaff(data.engineers);
          setCustomerArea(data.customer_area);
        })
        .catch(() => setStaff([]));
    }
  }, [loadTicket, canManage, user.role, user.id, id]);

  async function handleAddComment(e) {
    e.preventDefault();
    // Message text is required (enforced server-side too) -- the file
    // is always optional, attached to this same message if present.
    if (!commentBody.trim()) return;
    setPosting(true);
    setError(null);
    try {
      await commentsApi.create({
        ticket: id,
        body: commentBody,
        is_internal_note: isInternal,
      });
      setCommentBody("");
      setIsInternal(false);
      loadTicket();
    } catch (err) {
      setError(err.message);
    } finally {
      setPosting(false);
    }
  }

  async function handleStatusChange(newStatus) {
    try {
      await ticketsApi.update(id, { status: newStatus });
      loadTicket();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleAssign(userId) {
    setError(null);
    try {
      await ticketsApi.update(id, { assigned_to: userId || null });
      // The dropdown updating to show the new value isn't a strong
      // enough signal by itself -- easy to miss, and gave no
      // indication anything actually happened. This makes the result
      // of the action explicit and unmissable for a few seconds.
      if (userId) {
        const person = staff.find((s) => s.user === userId);
        setAssignConfirmation(`Assigned to ${person?.full_name || person?.username || "engineer"}.`);
      } else {
        setAssignConfirmation("Ticket unassigned.");
      }
      setTimeout(() => setAssignConfirmation(null), 5000);
      loadTicket();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDelete() {
    if (!window.confirm("Delete this ticket permanently? This can't be undone.")) return;
    try {
      await ticketsApi.delete(id);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.message);
    }
  }

  if (error) return <div className="error-banner">{error}</div>;
  if (!ticket) return <p>Loading ticket...</p>;

  return (
    <>
      {/* A fixed toast rather than a small line inside the sidebar --
          at 0.82rem tucked under a label it was genuinely easy to miss,
          which defeated the point of confirming at all. Matches the
          notification toast pattern used in Layout. */}
      {assignConfirmation && (
        <div className="toast-success" role="status">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
            <path d="M20 6L9 17l-5-5" />
          </svg>
          <span>{assignConfirmation}</span>
        </div>
      )}

      <Link to="/" style={{ fontSize: "0.88rem", display: "inline-block", marginBottom: 16 }}>
        &larr; Back to tickets
      </Link>

      <div className="page-header">
        <div>
          <h1>{ticket.title}</h1>
          {/* Status and priority read as plain text here. For staff
              the dropdown below is the authoritative control, so
              repeating it as a badge up here was the same fact twice. */}
          <p>
            {statusLabel(ticket.status)} &middot; {priorityLabel(ticket.priority)} priority
            &middot; raised by {ticket.created_by_username}
          </p>
        </div>
      </div>

      {/* Only for the engineer actually assigned -- someone else at the
          company has no reason to be requesting a customer's history
          for a job that isn't theirs. */}
      {user.role === "support_staff" && ticket.assigned_to === user.id && (
        <HistoryAccessRequestPanel ticket={ticket} />
      )}

      {reportLoaded && (
        <div style={{ marginBottom: 24 }}>
          <ServiceReportPanel ticket={ticket} report={report} onChanged={loadTicket} />
        </div>
      )}

      <div style={{ display: "flex", gap: 24, alignItems: "flex-start" }}>
        <div className="card" style={{ flex: 1, padding: 24 }}>
          <p style={{ color: "var(--ink-soft)", marginBottom: 20 }}>{ticket.description}</p>

          {/* Attached when the ticket was raised. The thread below is
              conversation only -- no further uploads by design. */}
          {(ticket.attachment_url || ticket.video_url) && (
            <div style={{ marginBottom: 24 }}>
              <div className="section-label">Attached by the customer</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-start" }}>
                {ticket.attachment_url && (
                  <a href={ticket.attachment_url} target="_blank" rel="noreferrer" className="file-chip">
                    {ticket.attachment_filename || "Attachment"}
                  </a>
                )}
                {ticket.video_url && (
                  <video
                    src={ticket.video_url}
                    controls
                    preload="metadata"
                    style={{ width: "100%", maxWidth: 380, borderRadius: "var(--radius-sm)", border: "1px solid var(--border)", background: "#000" }}
                  />
                )}
              </div>
            </div>
          )}

          <h3 style={{ fontSize: "0.95rem", marginBottom: 12 }}>Conversation</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 20 }}>
            {ticket.comments.length === 0 && (
              <p style={{ color: "var(--ink-soft)", fontSize: "0.9rem" }}>No replies yet.</p>
            )}
            {ticket.comments.map((c) => (
              <div
                key={c.id}
                className="card"
                style={{
                  padding: 12,
                  background: c.is_internal_note ? "var(--accent-warn-soft)" : "var(--paper)",
                  border: c.is_internal_note ? "1px solid var(--accent-warn)" : "1px solid var(--border)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <strong style={{ fontSize: "0.88rem" }}>{c.author_username}</strong>
                  <span className="mono" style={{ fontSize: "0.75rem", color: "var(--ink-soft)" }}>
                    {formatDateTime(c.created_at)}
                  </span>
                </div>
                {c.is_internal_note && (
                  <div style={{ fontSize: "0.72rem", color: "var(--accent-warn)", fontWeight: 600, marginBottom: 4 }}>
                    INTERNAL NOTE
                  </div>
                )}
                {/* Message and its file rendered together, one unit --
                    exactly the point of folding attachment onto the
                    comment itself rather than a separate list. */}
                <p style={{ margin: (c.attachment_url || c.video_url) ? "0 0 8px" : 0, fontSize: "0.9rem" }}>{c.body}</p>
                {(c.attachment_url || c.video_url) && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                    {c.attachment_url && (
                      <a
                        href={c.attachment_url}
                        target="_blank"
                        rel="noreferrer"
                        style={{
                          display: "inline-flex", alignItems: "center", gap: 6,
                          fontSize: "0.82rem", padding: "4px 10px", borderRadius: "var(--radius-sm)",
                          background: "var(--surface)", border: "1px solid var(--border)", textDecoration: "none",
                        }}
                      >
                        📎 {c.attachment_filename}
                      </a>
                    )}
                    {/* Played inline rather than offered as a download --
                        the whole point of attaching a screen recording is
                        that someone can just watch it. */}
                    {c.video_url && (
                      <video
                        src={c.video_url}
                        controls
                        preload="metadata"
                        style={{
                          width: "100%", maxWidth: 420, borderRadius: "var(--radius-sm)",
                          border: "1px solid var(--border)", background: "#000",
                        }}
                      />
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>

          <form onSubmit={handleAddComment}>
            <div className="field">
              <label htmlFor="comment">Add a reply</label>
              <textarea
                id="comment"
                value={commentBody}
                onChange={(e) => setCommentBody(e.target.value)}
                required
              />
            </div>

            {canManage && (
              <label style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16, fontSize: "0.88rem" }}>
                <input
                  type="checkbox"
                  checked={isInternal}
                  onChange={(e) => setIsInternal(e.target.checked)}
                />
                Internal note — never visible to the customer
              </label>
            )}

            <button type="submit" className="btn btn-primary" disabled={posting}>
              {posting ? "Sending..." : "Send reply"}
            </button>
          </form>

          {ticket.status_history.length > 0 && (
            <>
              <div className="section-label" style={{ marginTop: 28 }}>Status history</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {ticket.status_history.map((h) => (
                  <div key={h.id} style={{ fontSize: "0.85rem", color: "var(--ink-soft)" }}>
                    <span className="mono">{formatDateTime(h.changed_at)}</span>
                    {" — "}
                    {h.changed_by_username || "system"} changed status from{" "}
                    <strong>{STATUS_LABELS[h.from_status] || h.from_status || "—"}</strong> to{" "}
                    <strong>{STATUS_LABELS[h.to_status] || h.to_status}</strong>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {canManage && (
          <div className="card" style={{ width: 260, padding: 20 }}>
            <h3 style={{ fontSize: "0.9rem", marginBottom: 16 }}>Manage ticket</h3>

            <div className="field">
              <label htmlFor="status">Status</label>
              <select id="status" value={ticket.status} onChange={(e) => handleStatusChange(e.target.value)}>
                <option value="open">Open</option>
                <option value="in_progress">In progress</option>
                <option value="on_hold">On hold</option>
                <option value="resolved">Resolved</option>
                <option value="closed">Closed</option>
              </select>
            </div>

            <div className="field">
              <label htmlFor="assigned">Assigned to</label>
              {canReassign ? (
                <select
                  id="assigned"
                  value={ticket.assigned_to || ""}
                  onChange={(e) => handleAssign(e.target.value)}
                >
                  <option value="">Unassigned</option>
                  {staff.map((s) => (
                    <option key={s.user} value={s.user}>
                      {s.is_in_customer_area ? "★ " : ""}
                      {s.full_name || s.username}
                      {s.service_area ? ` — ${s.service_area}` : ""}
                    </option>
                  ))}
                </select>
              ) : (
                <>
                  <div style={{ fontSize: "0.92rem", padding: "9px 0" }}>
                    {ticket.assigned_to_username || "Unassigned"}
                  </div>
                  <span style={{ fontSize: "0.76rem", color: "var(--ink-soft)" }}>
                    Only the Service Manager or Service Department can assign.
                  </span>
                </>
              )}
            </div>

            {canReassign && (customerArea || ticket.customer_address) && (
              <div style={{ fontSize: "0.76rem", color: "var(--ink-soft)", marginTop: -8, marginBottom: 16 }}>
                {customerArea && (
                  <p style={{ margin: "0 0 2px" }}>
                    Customer is in <strong>{customerArea}</strong>. ★ marks engineers covering that area.
                  </p>
                )}
                {ticket.customer_address && (
                  <p style={{ margin: 0 }}>Address: {ticket.customer_address}</p>
                )}
              </div>
            )}

            <button
              type="button"
              className="btn btn-secondary"
              style={{ width: "100%", color: "var(--accent-urgent)" }}
              onClick={handleDelete}
            >
              Delete ticket
            </button>
          </div>
        )}
      </div>
    </>
  );
}
