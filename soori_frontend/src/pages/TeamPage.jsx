import { useEffect, useState } from "react";
import { supportStaffApi, subClientsApi, staffRolesApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";

const PLAN_LABELS = { basic: "Basic", pro: "Pro", enterprise: "Enterprise" };

const EMPTY_SUB_CLIENT_FORM = {
  username: "", email: "", company_name: "", phone: "", service_area: "",
  address: "", country: "",
  tax_registration_number: "", tax_document: null,
  contact_person_name: "", contact_person_email: "",
  billing_email: "", internal_notes: "",
  plan: "basic", subscription_period: "1_month", subscription_start: "",
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

export default function TeamPage() {
  const { user } = useAuth();
  const [staff, setStaff] = useState(null);
  const [roles, setRoles] = useState([]);
  const [subClients, setSubClients] = useState(null);
  const [error, setError] = useState(null);

  const [editingStaffId, setEditingStaffId] = useState(null);
  const [staffEditForm, setStaffEditForm] = useState(null);
  const [editingSubClientId, setEditingSubClientId] = useState(null);
  const [subClientEditForm, setSubClientEditForm] = useState(null);

  const [showAddStaff, setShowAddStaff] = useState(false);
  const [newStaff, setNewStaff] = useState({ username: "", email: "", role: "", department: "", phone: "", service_area: "" });
  const [showAddSubClient, setShowAddSubClient] = useState(false);
  const [newSubClient, setNewSubClient] = useState(EMPTY_SUB_CLIENT_FORM);
  const [submitting, setSubmitting] = useState(false);

  // Backend permission note (confirmed, not assumed): creating,
  // editing, or removing a profile requires the literal client_admin
  // role -- Soori Admin, even though they can see this page, gets a
  // 403 if they try. Soori Admin runs Clients/subscriptions; a Client
  // Admin runs their own team.
  const canEdit = user.role === "client_admin";

  function loadRoster() {
    // Roles are data now, not a hardcoded list -- fetch whatever this
    // company has actually defined.
    staffRolesApi.list().then(setRoles).catch(() => setRoles([]));
    Promise.all([supportStaffApi.list(), subClientsApi.list()])
      .then(([s, sc]) => {
        setStaff(s);
        setSubClients(sc);
      })
      .catch((err) => setError(err.message));
  }

  useEffect(loadRoster, []);

  async function handleAddStaff(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await supportStaffApi.create(newStaff);
      setNewStaff({ username: "", email: "", role: "", department: "", phone: "", service_area: "" });
      setShowAddStaff(false);
      loadRoster();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleAddSubClient(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await subClientsApi.create(newSubClient);
      setNewSubClient(EMPTY_SUB_CLIENT_FORM);
      setShowAddSubClient(false);
      loadRoster();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  function startEditingStaff(s) {
    setEditingStaffId(s.user);
    setStaffEditForm({ role: s.role || "", department: s.department || "", phone: s.phone || "", service_area: s.service_area || "", is_active_agent: s.is_active_agent });
  }

  async function saveStaffEdit(e, userId) {
    e.preventDefault();
    setError(null);
    try {
      await supportStaffApi.update(userId, staffEditForm);
      setEditingStaffId(null);
      loadRoster();
    } catch (err) {
      setError(err.message);
    }
  }

  async function removeStaff(s) {
    if (!window.confirm(`Remove ${s.full_name || s.username} from the staff roster?`)) return;
    setError(null);
    try {
      await supportStaffApi.delete(s.user);
      loadRoster();
    } catch (err) {
      setError(err.message);
    }
  }

  function startEditingSubClient(sc) {
    setEditingSubClientId(sc.user);
    setSubClientEditForm({
      company_name: sc.company_name || "", phone: sc.phone || "", service_area: sc.service_area || "",
      address: sc.address || "", country: sc.country || "",
      tax_registration_number: sc.tax_registration_number || "", tax_document: null,
      contact_person_name: sc.contact_person_name || "", contact_person_email: sc.contact_person_email || "",
      billing_email: sc.billing_email || "", internal_notes: sc.internal_notes || "",
      plan: sc.plan, status: sc.status,
      subscription_period: sc.subscription_period, subscription_start: sc.subscription_start || "",
    });
  }

  async function saveSubClientEdit(e, userId) {
    e.preventDefault();
    setError(null);
    try {
      await subClientsApi.update(userId, subClientEditForm);
      setEditingSubClientId(null);
      loadRoster();
    } catch (err) {
      setError(err.message);
    }
  }

  async function removeSubClient(sc) {
    if (!window.confirm(`Remove ${sc.username} as a sub-client?`)) return;
    setError(null);
    try {
      await subClientsApi.delete(sc.user);
      loadRoster();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <>
      <div className="page-header">
        <h1>Team</h1>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3 style={{ fontSize: "0.95rem", margin: 0 }}>Support Staff</h3>
        {canEdit && (
          <button className="btn btn-primary" style={{ padding: "6px 12px" }} onClick={() => setShowAddStaff((s) => !s)}>
            {showAddStaff ? "Cancel" : "+ Add Support Staff"}
          </button>
        )}
      </div>

      {showAddStaff && (
        <form onSubmit={handleAddStaff} className="card" style={{ padding: 20, marginBottom: 20, maxWidth: 480 }}>
          <p style={{ fontSize: "0.8rem", color: "var(--ink-soft)", marginTop: 0 }}>
            A temporary password is generated and emailed to them automatically.
          </p>
          <div className="field">
            <label>Username</label>
            <input value={newStaff.username} onChange={(e) => setNewStaff((f) => ({ ...f, username: e.target.value }))} required />
          </div>
          <div className="field">
            <label>Email</label>
            <input type="email" value={newStaff.email} onChange={(e) => setNewStaff((f) => ({ ...f, email: e.target.value }))} required />
          </div>
          <div className="field">
            <label>Role</label>
            <select value={newStaff.role} onChange={(e) => setNewStaff((f) => ({ ...f, role: e.target.value }))} required>
              <option value="">Select a role...</option>
              {roles.map((r) => (
                <option key={r.id} value={r.id}>{r.name}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Department</label>
            <input value={newStaff.department} onChange={(e) => setNewStaff((f) => ({ ...f, department: e.target.value }))} />
          </div>
          <div className="field">
            <label>Phone (for SMS notifications, once available)</label>
            <input value={newStaff.phone} onChange={(e) => setNewStaff((f) => ({ ...f, phone: e.target.value }))} />
          </div>
          <div className="field">
            <label>Service area</label>
            <input
              value={newStaff.service_area}
              onChange={(e) => setNewStaff((f) => ({ ...f, service_area: e.target.value }))}
              placeholder="e.g. Kathmandu"
            />
            <span style={{ fontSize: "0.76rem", color: "var(--ink-soft)" }}>
              For Field Engineers &mdash; used to route tickets to whoever covers the customer's area.
            </span>
          </div>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? "Creating..." : "Create + send login email"}
          </button>
        </form>
      )}

      {staff === null && <p>Loading...</p>}
      {staff && staff.length === 0 && <p style={{ color: "var(--ink-soft)" }}>No support staff yet.</p>}
      {staff && staff.length > 0 && (
        <div className="card" style={{ overflow: "hidden", marginBottom: 32 }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)", textAlign: "left" }}>
                <th style={thStyle}>Name</th>
                <th style={thStyle}>Username</th>
                <th style={thStyle}>Role</th>
                <th style={thStyle}>Department</th>
                <th style={thStyle}>Service area</th>
                <th style={thStyle}>Active</th>
                {canEdit && <th style={thStyle}></th>}
              </tr>
            </thead>
            <tbody>
              {staff.map((s) =>
                editingStaffId === s.user ? (
                  <tr key={s.user} style={{ borderBottom: "1px solid var(--border)", background: "var(--paper)" }}>
                    <td style={tdStyle} colSpan={7}>
                      <form onSubmit={(e) => saveStaffEdit(e, s.user)} style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
                        <div className="field" style={{ margin: 0 }}>
                          <label>Role</label>
                          <select
                            value={staffEditForm.role || ""}
                            onChange={(e) => setStaffEditForm((f) => ({ ...f, role: e.target.value }))}
                          >
                            {roles.map((r) => (
                              <option key={r.id} value={r.id}>{r.name}</option>
                            ))}
                          </select>
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                          <label>Department</label>
                          <input
                            value={staffEditForm.department}
                            onChange={(e) => setStaffEditForm((f) => ({ ...f, department: e.target.value }))}
                          />
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                          <label>Phone</label>
                          <input
                            value={staffEditForm.phone}
                            onChange={(e) => setStaffEditForm((f) => ({ ...f, phone: e.target.value }))}
                          />
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                          <label>Service area</label>
                          <input
                            value={staffEditForm.service_area}
                            onChange={(e) => setStaffEditForm((f) => ({ ...f, service_area: e.target.value }))}
                          />
                        </div>
                        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.88rem" }}>
                          <input
                            type="checkbox"
                            checked={staffEditForm.is_active_agent}
                            onChange={(e) => setStaffEditForm((f) => ({ ...f, is_active_agent: e.target.checked }))}
                          />
                          Active
                        </label>
                        <button type="submit" className="btn btn-primary">Save</button>
                        <button type="button" className="btn btn-secondary" onClick={() => setEditingStaffId(null)}>Cancel</button>
                      </form>
                    </td>
                  </tr>
                ) : (
                  <tr key={s.user} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={tdStyle}>{s.full_name || "—"}</td>
                    <td style={tdStyle}>{s.username}</td>
                    <td style={tdStyle}>{s.role_name || "—"}</td>
                    <td style={tdStyle}>{s.department || "—"}</td>
                    <td style={tdStyle}>{s.service_area || "—"}</td>
                    <td style={tdStyle}>{s.is_active_agent ? "Yes" : "No"}</td>
                    {canEdit && (
                      <td style={{ ...tdStyle, textAlign: "right", whiteSpace: "nowrap" }}>
                        <button className="btn btn-secondary" style={{ padding: "4px 10px", marginRight: 8 }} onClick={() => startEditingStaff(s)}>Edit</button>
                        <button className="btn btn-secondary" style={{ padding: "4px 10px", color: "var(--accent-urgent)" }} onClick={() => removeStaff(s)}>Remove</button>
                      </td>
                    )}
                  </tr>
                )
              )}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3 style={{ fontSize: "0.95rem", margin: 0 }}>Sub-Clients</h3>
        {canEdit && (
          <button className="btn btn-primary" style={{ padding: "6px 12px" }} onClick={() => setShowAddSubClient((s) => !s)}>
            {showAddSubClient ? "Cancel" : "+ Add Sub-Client"}
          </button>
        )}
      </div>

      {showAddSubClient && (
        <form onSubmit={handleAddSubClient} className="card" style={{ padding: 20, marginBottom: 20, maxWidth: 560 }}>
          <p style={{ fontSize: "0.8rem", color: "var(--ink-soft)", marginTop: 0 }}>
            A temporary password is generated and emailed to them automatically.
          </p>

          <h4 style={{ fontSize: "0.85rem", marginBottom: 8 }}>Company</h4>
          <div className="field">
            <label>Username</label>
            <input value={newSubClient.username} onChange={(e) => setNewSubClient((f) => ({ ...f, username: e.target.value }))} required />
          </div>
          <div className="field">
            <label>Email</label>
            <input type="email" value={newSubClient.email} onChange={(e) => setNewSubClient((f) => ({ ...f, email: e.target.value }))} required />
          </div>
          <div className="field">
            <label>Company name</label>
            <input value={newSubClient.company_name} onChange={(e) => setNewSubClient((f) => ({ ...f, company_name: e.target.value }))} />
          </div>
          <div className="field">
            <label>Address</label>
            <textarea value={newSubClient.address} onChange={(e) => setNewSubClient((f) => ({ ...f, address: e.target.value }))} />
          </div>
          <div className="field">
            <label>Country</label>
            <input value={newSubClient.country} onChange={(e) => setNewSubClient((f) => ({ ...f, country: e.target.value }))} />
          </div>
          <div className="field">
            <label>Service area</label>
            <input
              value={newSubClient.service_area}
              onChange={(e) => setNewSubClient((f) => ({ ...f, service_area: e.target.value }))}
              placeholder="e.g. Kathmandu"
            />
            <span style={{ fontSize: "0.76rem", color: "var(--ink-soft)" }}>
              Used to route their tickets to a nearby Field Engineer.
            </span>
          </div>

          <h4 style={{ fontSize: "0.85rem" }}>Tax / registration</h4>
          <div className="field">
            <label>PAN / VAT / tax registration number</label>
            <input value={newSubClient.tax_registration_number} onChange={(e) => setNewSubClient((f) => ({ ...f, tax_registration_number: e.target.value }))} />
          </div>
          <div className="field">
            <label>Supporting PAN/VAT document</label>
            <input type="file" onChange={(e) => setNewSubClient((f) => ({ ...f, tax_document: e.target.files?.[0] || null }))} required />
          </div>

          <h4 style={{ fontSize: "0.85rem" }}>Primary contact</h4>
          <div className="field">
            <label>Contact person name</label>
            <input value={newSubClient.contact_person_name} onChange={(e) => setNewSubClient((f) => ({ ...f, contact_person_name: e.target.value }))} />
          </div>
          <div className="field">
            <label>Contact person phone</label>
            <input value={newSubClient.phone} onChange={(e) => setNewSubClient((f) => ({ ...f, phone: e.target.value }))} />
          </div>
          <div className="field">
            <label>Contact person email</label>
            <input type="email" value={newSubClient.contact_person_email} onChange={(e) => setNewSubClient((f) => ({ ...f, contact_person_email: e.target.value }))} />
          </div>
          <div className="field">
            <label>Billing email (if different)</label>
            <input type="email" value={newSubClient.billing_email} onChange={(e) => setNewSubClient((f) => ({ ...f, billing_email: e.target.value }))} />
          </div>

          <h4 style={{ fontSize: "0.85rem" }}>Subscription</h4>
          <div className="field">
            <label>Plan</label>
            <select value={newSubClient.plan} onChange={(e) => setNewSubClient((f) => ({ ...f, plan: e.target.value }))}>
              <option value="basic">Basic</option>
              <option value="pro">Pro</option>
              <option value="enterprise">Enterprise</option>
            </select>
          </div>
          <div className="field">
            <label>Billing term</label>
            <select value={newSubClient.subscription_period} onChange={(e) => setNewSubClient((f) => ({ ...f, subscription_period: e.target.value }))}>
              <option value="1_month">1 Month</option>
              <option value="3_months">3 Months</option>
              <option value="6_months">6 Months</option>
              <option value="1_year">1 Year</option>
            </select>
          </div>
          <div className="field">
            <label>Subscription start</label>
            <input type="date" value={newSubClient.subscription_start} onChange={(e) => setNewSubClient((f) => ({ ...f, subscription_start: e.target.value }))} required />
            <span style={{ fontSize: "0.78rem", color: "var(--ink-soft)" }}>
              End date is calculated automatically from the start date + billing term.
            </span>
          </div>
          <div className="field">
            <label>Internal notes (your own account notes)</label>
            <textarea value={newSubClient.internal_notes} onChange={(e) => setNewSubClient((f) => ({ ...f, internal_notes: e.target.value }))} />
          </div>

          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? "Creating..." : "Create + send login email"}
          </button>
        </form>
      )}

      {subClients === null && <p>Loading...</p>}
      {subClients && subClients.length === 0 && <p style={{ color: "var(--ink-soft)" }}>No sub-clients yet.</p>}
      {subClients && subClients.length > 0 && (
        <div className="card" style={{ overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)", textAlign: "left" }}>
                <th style={thStyle}>Username</th>
                <th style={thStyle}>Company</th>
                <th style={thStyle}>Contact</th>
                <th style={thStyle}>Subscription</th>
                {canEdit && <th style={thStyle}></th>}
              </tr>
            </thead>
            <tbody>
              {subClients.map((sc) =>
                editingSubClientId === sc.user ? (
                  <tr key={sc.user} style={{ borderBottom: "1px solid var(--border)", background: "var(--paper)" }}>
                    <td style={tdStyle} colSpan={5}>
                      <form onSubmit={(e) => saveSubClientEdit(e, sc.user)} style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
                        <div className="field" style={{ margin: 0 }}>
                          <label>Company name</label>
                          <input value={subClientEditForm.company_name} onChange={(e) => setSubClientEditForm((f) => ({ ...f, company_name: e.target.value }))} />
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                          <label>Address</label>
                          <input value={subClientEditForm.address} onChange={(e) => setSubClientEditForm((f) => ({ ...f, address: e.target.value }))} />
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                          <label>Country</label>
                          <input value={subClientEditForm.country} onChange={(e) => setSubClientEditForm((f) => ({ ...f, country: e.target.value }))} />
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                          <label>Service area</label>
                          <input value={subClientEditForm.service_area} onChange={(e) => setSubClientEditForm((f) => ({ ...f, service_area: e.target.value }))} />
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                          <label>Tax reg. number</label>
                          <input value={subClientEditForm.tax_registration_number} onChange={(e) => setSubClientEditForm((f) => ({ ...f, tax_registration_number: e.target.value }))} />
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                          <label>Supporting PAN/VAT document</label>
                          <input type="file" onChange={(e) => setSubClientEditForm((f) => ({ ...f, tax_document: e.target.files?.[0] || null }))} />
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                          <label>Contact person name</label>
                          <input value={subClientEditForm.contact_person_name} onChange={(e) => setSubClientEditForm((f) => ({ ...f, contact_person_name: e.target.value }))} />
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                          <label>Contact phone</label>
                          <input value={subClientEditForm.phone} onChange={(e) => setSubClientEditForm((f) => ({ ...f, phone: e.target.value }))} />
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                          <label>Contact email</label>
                          <input type="email" value={subClientEditForm.contact_person_email} onChange={(e) => setSubClientEditForm((f) => ({ ...f, contact_person_email: e.target.value }))} />
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                          <label>Billing email</label>
                          <input type="email" value={subClientEditForm.billing_email} onChange={(e) => setSubClientEditForm((f) => ({ ...f, billing_email: e.target.value }))} />
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                          <label>Plan</label>
                          <select value={subClientEditForm.plan} onChange={(e) => setSubClientEditForm((f) => ({ ...f, plan: e.target.value }))}>
                            <option value="basic">Basic</option>
                            <option value="pro">Pro</option>
                            <option value="enterprise">Enterprise</option>
                          </select>
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                          <label>Status</label>
                          <select value={subClientEditForm.status} onChange={(e) => setSubClientEditForm((f) => ({ ...f, status: e.target.value }))}>
                            <option value="trial">Trial</option>
                            <option value="active">Active</option>
                            <option value="suspended">Suspended</option>
                            <option value="cancelled">Cancelled</option>
                          </select>
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                          <label>Billing term</label>
                          <select value={subClientEditForm.subscription_period} onChange={(e) => setSubClientEditForm((f) => ({ ...f, subscription_period: e.target.value }))}>
                            <option value="1_month">1 Month</option>
                            <option value="3_months">3 Months</option>
                            <option value="6_months">6 Months</option>
                            <option value="1_year">1 Year</option>
                          </select>
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                          <label>Subscription start (change to renew)</label>
                          <input type="date" value={subClientEditForm.subscription_start} onChange={(e) => setSubClientEditForm((f) => ({ ...f, subscription_start: e.target.value }))} />
                        </div>
                        <div className="field" style={{ margin: 0, minWidth: 240 }}>
                          <label>Internal notes</label>
                          <textarea value={subClientEditForm.internal_notes} onChange={(e) => setSubClientEditForm((f) => ({ ...f, internal_notes: e.target.value }))} />
                        </div>
                        <button type="submit" className="btn btn-primary">Save</button>
                        <button type="button" className="btn btn-secondary" onClick={() => setEditingSubClientId(null)}>Cancel</button>
                      </form>
                    </td>
                  </tr>
                ) : (
                  <tr key={sc.user} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={tdStyle}>{sc.username}</td>
                    <td style={tdStyle}>{sc.company_name || "—"}</td>
                    <td style={tdStyle}>
                      {sc.contact_person_name || sc.email || "—"}
                      {sc.contact_person_email && (
                        <div style={{ fontSize: "0.78rem", color: "var(--ink-soft)" }}>{sc.contact_person_email}</div>
                      )}
                    </td>
                    <td style={tdStyle}>
                      <div style={{ fontSize: "0.78rem", color: "var(--ink-soft)" }}>{PLAN_LABELS[sc.plan] || sc.plan}</div>
                      <span style={{ color: daysRemainingColor(sc.days_remaining), fontWeight: 600 }} className="mono">
                        {daysRemainingLabel(sc.days_remaining)}
                      </span>
                    </td>
                    {canEdit && (
                      <td style={{ ...tdStyle, textAlign: "right", whiteSpace: "nowrap" }}>
                        <button className="btn btn-secondary" style={{ padding: "4px 10px", marginRight: 8 }} onClick={() => startEditingSubClient(sc)}>Edit</button>
                        <button className="btn btn-secondary" style={{ padding: "4px 10px", color: "var(--accent-urgent)" }} onClick={() => removeSubClient(sc)}>Remove</button>
                      </td>
                    )}
                  </tr>
                )
              )}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

const thStyle = { padding: "12px 16px", fontSize: "0.8rem", color: "var(--ink-soft)", fontWeight: 600 };
const tdStyle = { padding: "12px 16px", fontSize: "0.92rem" };
