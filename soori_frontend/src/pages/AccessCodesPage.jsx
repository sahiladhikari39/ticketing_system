import { useEffect, useState } from "react";
import { accessCodesApi, subClientsApi, historyAccessRequestsApi } from "../api/endpoints";
import { formatDate, formatDateTime } from "../utils/format";

const SCOPE_LABELS = {
  knowledge_base: "Knowledge Base",
  customer_history: "Customer history",
};

function fromNow(hours) {
  const d = new Date();
  d.setHours(d.getHours() + hours);
  // datetime-local wants YYYY-MM-DDTHH:mm with no timezone suffix
  return d.toISOString().slice(0, 16);
}

// The common cases, one click each -- an engineer needing a customer's
// history for the job in front of them wants "1 hour from now", not to
// calculate and type a date by hand. An intern's training access is a
// longer-lived thing, so that gets its own preset too.
const DURATION_PRESETS = [
  { label: "1 hour", hours: 1 },
  { label: "8 hours", hours: 8 },
  { label: "1 day", hours: 24 },
  { label: "1 week", hours: 24 * 7 },
  { label: "6 weeks", hours: 24 * 7 * 6 },
];

const EMPTY_FORM = {
  scope: "knowledge_base",
  label: "",
  customer: "",
  expires_at: fromNow(1),
  max_uses: "",
  recipient_email: "",
};

export default function AccessCodesPage() {
  const [codes, setCodes] = useState(null);
  const [requests, setRequests] = useState(null);
  const [customers, setCustomers] = useState([]);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  // Holds the freshly-issued code. This is the ONLY moment the secret
  // exists in the app -- it isn't stored and can't be fetched again.
  const [justIssued, setJustIssued] = useState(null);

  function load() {
    accessCodesApi.list().then(setCodes).catch((err) => setError(err.message));
    historyAccessRequestsApi.list().then(setRequests).catch(() => setRequests([]));
  }

  async function handleApproveRequest(request) {
    setError(null);
    try {
      await historyAccessRequestsApi.approve(request.id, 4);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDenyRequest(request) {
    setError(null);
    try {
      await historyAccessRequestsApi.deny(request.id);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
    subClientsApi.list().then(setCustomers).catch(() => setCustomers([]));
  }, []);

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function handleIssue(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const payload = {
        scope: form.scope,
        label: form.label,
        expires_at: new Date(form.expires_at).toISOString(),
      };
      if (form.scope === "customer_history") payload.customer = form.customer;
      if (form.max_uses) payload.max_uses = Number(form.max_uses);
      if (form.recipient_email) payload.recipient_email = form.recipient_email;

      const created = await accessCodesApi.issue(payload);
      setJustIssued(created);
      setForm({ ...EMPTY_FORM, expires_at: fromNow(1) });
      setShowForm(false);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRevoke(code) {
    if (!window.confirm(`Revoke "${code.label}"? It'll stop working immediately.`)) return;
    setError(null);
    try {
      await accessCodesApi.revoke(code.id);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Access codes</h1>
          <p>
            Temporary read-only access for people without accounts — an intern on placement,
            or a customer contact checking their own service history.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm((s) => !s)}>
          {showForm ? "Cancel" : "Issue a code"}
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {/* Engineer-initiated requests -- separate from the codes YOU
          issue below, since these came from someone ELSE asking for
          access rather than you proactively granting it. */}
      {requests && requests.filter((r) => r.status === "pending").length > 0 && (
        <div className="card" style={{ padding: 20, marginBottom: 24 }}>
          <p className="section-label">Pending access requests</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {requests
              .filter((r) => r.status === "pending")
              .map((r) => (
                <div
                  key={r.id}
                  style={{
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    gap: 12, padding: "10px 0", borderBottom: "1px solid var(--border)",
                  }}
                >
                  <div>
                    <div style={{ fontSize: "0.92rem", fontWeight: 600 }}>
                      {r.requested_by_username} &middot; {r.customer_company || r.customer_username}
                    </div>
                    <div style={{ fontSize: "0.8rem", color: "var(--ink-soft)" }}>
                      Ticket: {r.ticket_title}
                      {r.reason && ` \u2014 ${r.reason}`}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                    <button
                      className="btn btn-secondary"
                      style={{ padding: "5px 12px", color: "var(--accent-urgent)" }}
                      onClick={() => handleDenyRequest(r)}
                    >
                      Deny
                    </button>
                    <button
                      className="btn btn-primary"
                      style={{ padding: "5px 12px" }}
                      onClick={() => handleApproveRequest(r)}
                    >
                      Approve (4 hours)
                    </button>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* The signature moment of this screen. Oversized and monospaced
          because this gets read aloud or copied onto paper for someone
          who has no account -- and it genuinely cannot be shown again. */}
      {justIssued && (
        <div className="secret-reveal">
          <p className="section-label" style={{ marginBottom: 16 }}>
            Code issued — write this down now
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 16 }}>
            <div>
              <div className="secret-reveal-label">Username</div>
              <div className="secret-reveal-value">{justIssued.username}</div>
            </div>
            <div>
              <div className="secret-reveal-label">Code</div>
              <div className="secret-reveal-value">{justIssued.secret}</div>
            </div>
          </div>
          <p style={{ fontSize: "0.85rem", color: "var(--primary-hover)", margin: "0 0 14px", fontWeight: 600 }}>
            {justIssued.secret_notice}
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              className="btn btn-secondary"
              onClick={() => {
                navigator.clipboard?.writeText(
                  `Username: ${justIssued.username}\nCode: ${justIssued.secret}`
                );
              }}
            >
              Copy both
            </button>
            <button className="btn btn-secondary" onClick={() => setJustIssued(null)}>
              I've saved it
            </button>
          </div>
        </div>
      )}

      {showForm && (
        <form onSubmit={handleIssue} className="card" style={{ padding: 24, marginBottom: 24, maxWidth: 520 }}>
          <p className="section-label">New code</p>

          <div className="field">
            <label htmlFor="scope">What it unlocks</label>
            <select id="scope" value={form.scope} onChange={(e) => set("scope", e.target.value)}>
              <option value="knowledge_base">Knowledge Base — training material</option>
              <option value="customer_history">Customer history — one customer's own reports</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="label">Who is it for</label>
            <input
              id="label"
              value={form.label}
              onChange={(e) => set("label", e.target.value)}
              placeholder="Intern — Ramesh, August batch"
              required
            />
            <span style={{ fontSize: "0.76rem", color: "var(--ink-soft)" }}>
              Just a note to help you tell your codes apart later.
            </span>
          </div>

          {form.scope === "customer_history" && (
            <div className="field">
              <label htmlFor="customer">Which customer</label>
              <select id="customer" value={form.customer} onChange={(e) => set("customer", e.target.value)} required>
                <option value="">Select a customer...</option>
                {customers.map((c) => (
                  <option key={c.user} value={c.user}>
                    {c.company_name || c.username}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="field">
            <label>How long</label>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
              {DURATION_PRESETS.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  className="btn btn-secondary"
                  style={{ padding: "5px 12px", fontSize: "0.82rem" }}
                  onClick={() => set("expires_at", fromNow(preset.hours))}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          <div className="field">
            <label htmlFor="expires">Stops working on</label>
            <input
              id="expires"
              type="datetime-local"
              value={form.expires_at}
              onChange={(e) => set("expires_at", e.target.value)}
              required
            />
          </div>

          <div className="field">
            <label htmlFor="maxuses">Use limit (optional)</label>
            <input
              id="maxuses"
              type="number"
              min="1"
              value={form.max_uses}
              onChange={(e) => set("max_uses", e.target.value)}
              placeholder="Leave blank for unlimited until expiry"
            />
          </div>

          <div className="field">
            <label htmlFor="recipient-email">Email it to (optional)</label>
            <input
              id="recipient-email"
              type="email"
              value={form.recipient_email}
              onChange={(e) => set("recipient_email", e.target.value)}
              placeholder="intern@example.com"
            />
            <span style={{ fontSize: "0.76rem", color: "var(--ink-soft)" }}>
              Sends the username and code directly. It still only shows on screen once either way.
            </span>
          </div>

          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? "Issuing..." : "Issue code"}
          </button>
        </form>
      )}

      {codes === null && !error && <p>Loading...</p>}

      {codes && codes.length === 0 && (
        <div className="empty-state card">
          <h3>No codes issued</h3>
          <p>Issue one to give an intern or a customer contact temporary read-only access.</p>
        </div>
      )}

      {codes && codes.length > 0 && (
        <div className="card" style={{ overflow: "hidden" }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>For</th>
                <th>Unlocks</th>
                <th>Username</th>
                <th>Expires</th>
                <th>Used</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {codes.map((code) => (
                <tr key={code.id}>
                  <td>
                    {code.label}
                    {code.customer_username && (
                      <div style={{ fontSize: "0.78rem", color: "var(--ink-soft)" }}>
                        {code.customer_username}
                      </div>
                    )}
                  </td>
                  <td>{SCOPE_LABELS[code.scope] || code.scope}</td>
                  <td className="mono" style={{ fontSize: "0.85rem" }}>{code.username}</td>
                  <td className="mono" style={{ fontSize: "0.85rem" }}>{formatDate(code.expires_at)}</td>
                  <td className="mono" style={{ fontSize: "0.85rem" }}>
                    {code.use_count}
                    {code.max_uses ? ` / ${code.max_uses}` : ""}
                    {code.last_used_at && (
                      <div style={{ fontSize: "0.72rem", color: "var(--ink-soft)" }}>
                        {formatDateTime(code.last_used_at)}
                      </div>
                    )}
                  </td>
                  <td>
                    <span style={{ color: code.status === "active" ? "var(--ink)" : "var(--ink-soft)" }}>
                      {code.status.charAt(0).toUpperCase() + code.status.slice(1)}
                    </span>
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {code.status === "active" && (
                      <button
                        className="btn btn-secondary"
                        style={{ padding: "4px 10px", color: "var(--accent-urgent)" }}
                        onClick={() => handleRevoke(code)}
                      >
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
