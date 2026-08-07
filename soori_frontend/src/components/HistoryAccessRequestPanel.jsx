import { useEffect, useState } from "react";
import { historyAccessRequestsApi } from "../api/endpoints";

/**
 * Lets the ASSIGNED engineer ask for temporary access to the
 * customer's full service history -- distinct from
 * knowledge.AccessCode, which only the Service Manager could issue
 * proactively. Before this, an engineer preparing for a repeat fault
 * had no way to ask; they had to hope someone thought of it.
 */
export default function HistoryAccessRequestPanel({ ticket }) {
  const [existing, setExisting] = useState(null);
  const [reason, setReason] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  function load() {
    historyAccessRequestsApi
      .list()
      .then((all) => setExisting(all.find((r) => r.ticket === ticket.id) || null))
      .catch(() => setExisting(null));
  }

  useEffect(load, [ticket.id]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await historyAccessRequestsApi.create(ticket.id, reason);
      setShowForm(false);
      setReason("");
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (existing === null && !showForm) {
    return (
      <div className="card" style={{ padding: 20, marginBottom: 24 }}>
        <p className="section-label">Customer history</p>
        <p style={{ fontSize: "0.88rem", color: "var(--ink-soft)", marginBottom: 12 }}>
          Need to see this customer's past visits before starting? Request temporary access --
          the Service Manager will review it.
        </p>
        <button className="btn btn-secondary" onClick={() => setShowForm(true)}>
          Request history access
        </button>
      </div>
    );
  }

  if (showForm) {
    return (
      <form onSubmit={handleSubmit} className="card" style={{ padding: 20, marginBottom: 24 }}>
        <p className="section-label">Request history access</p>
        {error && <div className="error-banner">{error}</div>}
        <div className="field">
          <label htmlFor="reason">Why (optional)</label>
          <input
            id="reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Repeat fault, want to see what was tried before"
          />
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? "Sending..." : "Send request"}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>
            Cancel
          </button>
        </div>
      </form>
    );
  }

  const statusCopy = {
    pending: "Waiting for the Service Manager to review.",
    approved: "Approved -- check your email for the temporary login.",
    denied: "This request wasn't approved.",
  };

  return (
    <div className="card" style={{ padding: 20, marginBottom: 24 }}>
      <p className="section-label">Customer history</p>
      <p style={{ fontSize: "0.9rem", margin: 0 }}>
        {statusCopy[existing.status] || existing.status}
      </p>
    </div>
  );
}
