import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { clientsApi } from "../api/endpoints";

const PLAN_LABELS = { basic: "Basic", pro: "Pro", enterprise: "Enterprise" };
const STATUS_LABELS = { trial: "Trial", active: "Active", suspended: "Suspended", cancelled: "Cancelled" };

const EMPTY_FORM = {
  name: "", plan: "basic", subscription_period: "1_month", subscription_start: "",
  admin_username: "", admin_email: "",
  address: "", country: "",
  tax_registration_number: "", tax_document: null,
  contact_person_name: "", contact_person_phone: "", contact_person_email: "",
  billing_email: "", internal_notes: "",
};

function daysRemainingLabel(days) {
  if (days === null || days === undefined) return "—";
  if (days < 0) return `Expired ${Math.abs(days)}d ago`;
  return `${days}d left`;
}

function daysRemainingColor(days) {
  if (days === null || days === undefined) return "var(--ink-soft)";
  if (days < 0) return "var(--accent-urgent)";
  if (days <= 14) return "var(--accent-warn)";
  return "var(--accent-success)";
}

export default function ClientsPage() {
  const [clients, setClients] = useState(null);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);

  function loadClients() {
    clientsApi.list().then(setClients).catch((err) => setError(err.message));
  }

  useEffect(loadClients, []);

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function handleCreate(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await clientsApi.create(form);
      setForm(EMPTY_FORM);
      setShowForm(false);
      loadClients();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Clients</h1>
          <p>Every company subscribed to Soori — billing and account details only.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm((s) => !s)}>
          {showForm ? "Cancel" : "+ New client"}
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {showForm && (
        <form onSubmit={handleCreate} className="card" style={{ padding: 20, marginBottom: 24, maxWidth: 560 }}>
          <h3 style={{ fontSize: "0.88rem", marginTop: 0 }}>Company</h3>
          <div className="field">
            <label>Company name</label>
            <input value={form.name} onChange={(e) => update("name", e.target.value)} required />
          </div>
          <div className="field">
            <label>Address</label>
            <textarea value={form.address} onChange={(e) => update("address", e.target.value)} />
          </div>
          <div className="field">
            <label>Country</label>
            <input value={form.country} onChange={(e) => update("country", e.target.value)} />
          </div>

          <h3 style={{ fontSize: "0.88rem" }}>Tax / registration</h3>
          <div className="field">
            <label>PAN / VAT / tax registration number</label>
            <input value={form.tax_registration_number} onChange={(e) => update("tax_registration_number", e.target.value)} />
          </div>
          <div className="field">
            <label>Supporting PAN/VAT document</label>
            <input type="file" onChange={(e) => update("tax_document", e.target.files?.[0] || null)} required />
          </div>

          <h3 style={{ fontSize: "0.88rem" }}>Primary contact</h3>
          <div className="field">
            <label>Contact person name</label>
            <input value={form.contact_person_name} onChange={(e) => update("contact_person_name", e.target.value)} />
          </div>
          <div className="field">
            <label>Contact person phone</label>
            <input value={form.contact_person_phone} onChange={(e) => update("contact_person_phone", e.target.value)} />
          </div>
          <div className="field">
            <label>Contact person email</label>
            <input type="email" value={form.contact_person_email} onChange={(e) => update("contact_person_email", e.target.value)} />
          </div>
          <div className="field">
            <label>Billing email (if different)</label>
            <input type="email" value={form.billing_email} onChange={(e) => update("billing_email", e.target.value)} />
          </div>

          <h3 style={{ fontSize: "0.88rem" }}>Subscription</h3>
          <div className="field">
            <label>Plan</label>
            <select value={form.plan} onChange={(e) => update("plan", e.target.value)}>
              <option value="basic">Basic</option>
              <option value="pro">Pro</option>
              <option value="enterprise">Enterprise</option>
            </select>
          </div>
          <div className="field">
            <label>Billing term</label>
            <select value={form.subscription_period} onChange={(e) => update("subscription_period", e.target.value)}>
              <option value="1_month">1 Month</option>
              <option value="3_months">3 Months</option>
              <option value="6_months">6 Months</option>
              <option value="1_year">1 Year</option>
            </select>
          </div>
          <div className="field">
            <label>Subscription start</label>
            <input type="date" value={form.subscription_start} onChange={(e) => update("subscription_start", e.target.value)} required />
            <span style={{ fontSize: "0.78rem", color: "var(--ink-soft)" }}>
              End date is calculated automatically from the start date + billing term.
            </span>
          </div>
          <div className="field">
            <label>Internal notes (Soori's own account notes)</label>
            <textarea value={form.internal_notes} onChange={(e) => update("internal_notes", e.target.value)} />
          </div>

          <h3 style={{ fontSize: "0.88rem" }}>First login</h3>
          <div className="field">
            <label>Client Admin username</label>
            <input value={form.admin_username} onChange={(e) => update("admin_username", e.target.value)} required />
          </div>
          <div className="field">
            <label>Client Admin email</label>
            <input type="email" value={form.admin_email} onChange={(e) => update("admin_email", e.target.value)} required />
            <span style={{ fontSize: "0.78rem", color: "var(--ink-soft)" }}>
              A temporary password gets generated and emailed to this address.
            </span>
          </div>

          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? "Creating..." : "Create client"}
          </button>
        </form>
      )}

      {clients === null && <p>Loading...</p>}

      {clients && clients.length > 0 && (
        <div className="card" style={{ overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)", textAlign: "left" }}>
                <th style={thStyle}>Name</th>
                <th style={thStyle}>Plan</th>
                <th style={thStyle}>Status</th>
                <th style={thStyle}>Contact</th>
                <th style={thStyle}>Subscription</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((c) => (
                <tr key={c.id} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={tdStyle}>
                    <Link to={`/clients/${c.id}`} style={{ fontWeight: 600, textDecoration: "none" }}>
                      {c.name}
                    </Link>
                  </td>
                  <td style={tdStyle}>{PLAN_LABELS[c.plan] || c.plan}</td>
                  <td style={tdStyle}>{STATUS_LABELS[c.status] || c.status}</td>
                  <td style={tdStyle}>
                    {c.contact_person_name || "—"}
                    {c.contact_person_email && (
                      <div style={{ fontSize: "0.78rem", color: "var(--ink-soft)" }}>{c.contact_person_email}</div>
                    )}
                  </td>
                  <td style={tdStyle}>
                    <span style={{ color: daysRemainingColor(c.days_remaining), fontWeight: 600 }} className="mono">
                      {daysRemainingLabel(c.days_remaining)}
                    </span>
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

const thStyle = { padding: "12px 16px", fontSize: "0.8rem", color: "var(--ink-soft)", fontWeight: 600 };
const tdStyle = { padding: "12px 16px", fontSize: "0.92rem" };
