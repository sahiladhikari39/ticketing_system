import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { clientsApi } from "../api/endpoints";
import { formatDate } from "../utils/format";

const PLAN_LABELS = { basic: "Basic", pro: "Pro", enterprise: "Enterprise" };
const STATUS_LABELS = { trial: "Trial", active: "Active", suspended: "Suspended", cancelled: "Cancelled" };
const PERIOD_LABELS = { "1_month": "1 Month", "3_months": "3 Months", "6_months": "6 Months", "1_year": "1 Year" };

function daysRemainingLabel(days) {
  if (days === null || days === undefined) return "No end date set";
  if (days < 0) return `Expired ${Math.abs(days)} day${Math.abs(days) === 1 ? "" : "s"} ago`;
  if (days === 0) return "Expires today";
  return `${days} day${days === 1 ? "" : "s"} remaining`;
}

function daysRemainingColor(days) {
  if (days === null || days === undefined) return "var(--ink-soft)";
  if (days < 0) return "var(--accent-urgent)";
  if (days <= 14) return "var(--accent-warn)";
  return "var(--accent-success)";
}

const FIELD_ROWS = [
  { section: "Subscription", fields: [
    ["plan", "Plan", (c) => PLAN_LABELS[c.plan] || c.plan],
    ["status", "Status", (c) => STATUS_LABELS[c.status] || c.status],
    ["subscription_period", "Billing term", (c) => PERIOD_LABELS[c.subscription_period] || c.subscription_period],
    ["subscription_start", "Start date", (c) => c.subscription_start],
    ["subscription_end", "End date", (c) => c.subscription_end || "—"],
  ]},
  { section: "Company profile", fields: [
    ["address", "Address", (c) => c.address || "—"],
    ["country", "Country", (c) => c.country || "—"],
  ]},
  { section: "Tax / registration", fields: [
    ["tax_registration_number", "PAN / VAT / tax registration number", (c) => c.tax_registration_number || "—"],
  ]},
  { section: "Primary contact", fields: [
    ["contact_person_name", "Contact person", (c) => c.contact_person_name || "—"],
    ["contact_person_phone", "Phone", (c) => c.contact_person_phone || "—"],
    ["contact_person_email", "Email", (c) => c.contact_person_email || "—"],
    ["billing_email", "Billing email", (c) => c.billing_email || "—"],
  ]},
];

export default function ClientDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [client, setClient] = useState(null);
  const [error, setError] = useState(null);
  const [editMode, setEditMode] = useState(false);
  const [editForm, setEditForm] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  function loadClient() {
    clientsApi.get(id).then(setClient).catch((err) => setError(err.message));
  }

  useEffect(loadClient, [id]);

  function startEditing() {
    setEditForm({
      name: client.name,
      plan: client.plan,
      status: client.status,
      subscription_period: client.subscription_period,
      subscription_start: client.subscription_start,
      address: client.address || "",
      country: client.country || "",
      tax_registration_number: client.tax_registration_number || "",
      tax_document: null,
      contact_person_name: client.contact_person_name || "",
      contact_person_phone: client.contact_person_phone || "",
      contact_person_email: client.contact_person_email || "",
      billing_email: client.billing_email || "",
      internal_notes: client.internal_notes || "",
    });
    setEditMode(true);
  }

  async function handleSave(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await clientsApi.update(id, editForm);
      setEditMode(false);
      loadClient();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm(`Remove ${client.name} from Soori? This can't be undone.`)) return;
    try {
      await clientsApi.delete(id);
      navigate("/clients", { replace: true });
    } catch (err) {
      setError(err.message);
    }
  }

  if (error) return <div className="error-banner">{error}</div>;
  if (!client) return <p>Loading...</p>;

  return (
    <>
      <Link to="/clients" style={{ fontSize: "0.88rem", display: "inline-block", marginBottom: 16 }}>
        &larr; Back to clients
      </Link>

      <div className="page-header">
        <div>
          <h1>{client.name}</h1>
          <p>Onboarded {formatDate(client.created_at)}</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {!editMode && (
            <>
              <button className="btn btn-secondary" onClick={startEditing}>Edit</button>
              <button className="btn btn-secondary" style={{ color: "var(--accent-urgent)" }} onClick={handleDelete}>Delete</button>
            </>
          )}
        </div>
      </div>

      <div className="card" style={{ padding: 20, marginBottom: 24, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div style={{ fontSize: "0.82rem", color: "var(--ink-soft)" }}>
            {PLAN_LABELS[client.plan] || client.plan} plan &middot; {PERIOD_LABELS[client.subscription_period] || client.subscription_period}
          </div>
          <div style={{ fontSize: "1.3rem", fontWeight: 700, color: daysRemainingColor(client.days_remaining) }}>
            {daysRemainingLabel(client.days_remaining)}
          </div>
        </div>
        <div style={{ textAlign: "right", fontSize: "0.85rem", color: "var(--ink-soft)" }}>
          <div>{client.subscription_start} &rarr; {client.subscription_end || "—"}</div>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {editMode ? (
        <form onSubmit={handleSave} className="card" style={{ padding: 24, maxWidth: 560 }}>
          <h3 style={{ fontSize: "0.88rem", marginTop: 0 }}>Company</h3>
          <div className="field">
            <label>Company name</label>
            <input value={editForm.name} onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))} required />
          </div>
          <div className="field">
            <label>Address</label>
            <textarea value={editForm.address} onChange={(e) => setEditForm((f) => ({ ...f, address: e.target.value }))} />
          </div>
          <div className="field">
            <label>Country</label>
            <input value={editForm.country} onChange={(e) => setEditForm((f) => ({ ...f, country: e.target.value }))} />
          </div>

          <h3 style={{ fontSize: "0.88rem" }}>Tax / registration</h3>
          <div className="field">
            <label>PAN / VAT / tax registration number</label>
            <input value={editForm.tax_registration_number} onChange={(e) => setEditForm((f) => ({ ...f, tax_registration_number: e.target.value }))} />
          </div>
          <div className="field">
            <label>Supporting PAN/VAT document</label>
            <input type="file" onChange={(e) => setEditForm((f) => ({ ...f, tax_document: e.target.files?.[0] || null }))} />
            {client.tax_document && (
              <span style={{ fontSize: "0.78rem" }}>
                Current: <a href={client.tax_document} target="_blank" rel="noreferrer">view document</a>
              </span>
            )}
          </div>

          <h3 style={{ fontSize: "0.88rem" }}>Primary contact</h3>
          <div className="field">
            <label>Contact person name</label>
            <input value={editForm.contact_person_name} onChange={(e) => setEditForm((f) => ({ ...f, contact_person_name: e.target.value }))} />
          </div>
          <div className="field">
            <label>Contact person phone</label>
            <input value={editForm.contact_person_phone} onChange={(e) => setEditForm((f) => ({ ...f, contact_person_phone: e.target.value }))} />
          </div>
          <div className="field">
            <label>Contact person email</label>
            <input type="email" value={editForm.contact_person_email} onChange={(e) => setEditForm((f) => ({ ...f, contact_person_email: e.target.value }))} />
          </div>
          <div className="field">
            <label>Billing email</label>
            <input type="email" value={editForm.billing_email} onChange={(e) => setEditForm((f) => ({ ...f, billing_email: e.target.value }))} />
          </div>

          <h3 style={{ fontSize: "0.88rem" }}>Subscription</h3>
          <div className="field">
            <label>Plan</label>
            <select value={editForm.plan} onChange={(e) => setEditForm((f) => ({ ...f, plan: e.target.value }))}>
              <option value="basic">Basic</option>
              <option value="pro">Pro</option>
              <option value="enterprise">Enterprise</option>
            </select>
          </div>
          <div className="field">
            <label>Status</label>
            <select value={editForm.status} onChange={(e) => setEditForm((f) => ({ ...f, status: e.target.value }))}>
              <option value="trial">Trial</option>
              <option value="active">Active</option>
              <option value="suspended">Suspended</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </div>
          <div className="field">
            <label>Billing term</label>
            <select value={editForm.subscription_period} onChange={(e) => setEditForm((f) => ({ ...f, subscription_period: e.target.value }))}>
              <option value="1_month">1 Month</option>
              <option value="3_months">3 Months</option>
              <option value="6_months">6 Months</option>
              <option value="1_year">1 Year</option>
            </select>
          </div>
          <div className="field">
            <label>Subscription start (change this to renew from a new date)</label>
            <input type="date" value={editForm.subscription_start} onChange={(e) => setEditForm((f) => ({ ...f, subscription_start: e.target.value }))} required />
            <span style={{ fontSize: "0.78rem", color: "var(--ink-soft)" }}>
              End date is calculated automatically from the start date + billing term.
            </span>
          </div>
          <div className="field">
            <label>Internal notes (Soori's own account notes)</label>
            <textarea value={editForm.internal_notes} onChange={(e) => setEditForm((f) => ({ ...f, internal_notes: e.target.value }))} />
          </div>

          <div style={{ display: "flex", gap: 8 }}>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? "Saving..." : "Save changes"}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setEditMode(false)}>Cancel</button>
          </div>
        </form>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {FIELD_ROWS.map((group) => (
            <div key={group.section} className="card" style={{ padding: 20 }}>
              <h3 style={{ fontSize: "0.88rem", marginTop: 0, marginBottom: 12 }}>{group.section}</h3>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                {group.fields.map(([key, label, getValue]) => (
                  <div key={key}>
                    <div style={{ fontSize: "0.78rem", color: "var(--ink-soft)" }}>{label}</div>
                    <div style={{ fontSize: "0.92rem" }}>{getValue(client)}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}

          <div className="card" style={{ padding: 20 }}>
            <h3 style={{ fontSize: "0.88rem", marginTop: 0, marginBottom: 12 }}>Registration document</h3>
            {client.tax_document ? (
              <a href={client.tax_document} target="_blank" rel="noreferrer">View uploaded document</a>
            ) : (
              <p style={{ margin: 0, color: "var(--ink-soft)", fontSize: "0.9rem" }}>No document uploaded.</p>
            )}
          </div>

          {client.internal_notes && (
            <div className="card" style={{ padding: 20 }}>
              <h3 style={{ fontSize: "0.88rem", marginTop: 0, marginBottom: 12 }}>Internal notes</h3>
              <p style={{ margin: 0, fontSize: "0.9rem", whiteSpace: "pre-wrap" }}>{client.internal_notes}</p>
            </div>
          )}
        </div>
      )}
    </>
  );
}
