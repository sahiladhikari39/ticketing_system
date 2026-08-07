import { useEffect, useState } from "react";
import { staffRolesApi } from "../api/endpoints";

const EMPTY_FORM = { name: "", description: "", permissions: [] };

/**
 * Lets a Service Manager define the roles their own organisation needs
 * and choose what each can do -- no developer, no deployment.
 *
 * The permission list comes from the server with every response rather
 * than being hardcoded here, so the two can't drift apart. If a new
 * permission is added to the backend it appears here automatically.
 */
export default function StaffRolesPage() {
  const [roles, setRoles] = useState(null);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState(null);
  const [busy, setBusy] = useState(false);

  function load() {
    staffRolesApi.list().then(setRoles).catch((err) => setError(err.message));
  }

  useEffect(load, []);

  // Every role response ships the full permission vocabulary, so any
  // one of them is a valid source for the checkbox list.
  const allPermissions = roles?.[0]?.available_permissions || [];

  function togglePermission(code) {
    setForm((f) => ({
      ...f,
      permissions: f.permissions.includes(code)
        ? f.permissions.filter((p) => p !== code)
        : [...f.permissions, code],
    }));
  }

  function startCreate() {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setShowForm(true);
  }

  function startEdit(role) {
    setForm({
      name: role.name,
      description: role.description || "",
      permissions: [...(role.permissions || [])],
    });
    setEditingId(role.id);
    setShowForm(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (editingId) {
        await staffRolesApi.update(editingId, form);
      } else {
        await staffRolesApi.create(form);
      }
      setForm(EMPTY_FORM);
      setEditingId(null);
      setShowForm(false);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(role) {
    if (!window.confirm(`Delete the "${role.name}" role?`)) return;
    setError(null);
    try {
      await staffRolesApi.delete(role.id);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Roles</h1>
          <p>
            Define the jobs in your service team and what each one can do.
            Changes take effect immediately.
          </p>
        </div>
        <button className="btn btn-primary" onClick={startCreate}>
          Add a role
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {showForm && (
        <form onSubmit={handleSubmit} className="card" style={{ padding: 24, marginBottom: 24, maxWidth: 560 }}>
          <p className="section-label">{editingId ? "Edit role" : "New role"}</p>

          <div className="field">
            <label htmlFor="role-name">Role name</label>
            <input
              id="role-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="Regional Lead"
              required
            />
          </div>

          <div className="field">
            <label htmlFor="role-desc">What this role does</label>
            <input
              id="role-desc"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              placeholder="Senior engineer who also assigns work in their region."
            />
          </div>

          <div className="field">
            <label>What they can do</label>
            <div className="perm-grid">
              {allPermissions.map((perm) => {
                const on = form.permissions.includes(perm.code);
                return (
                  <label key={perm.code} className={`perm-option${on ? " is-on" : ""}`}>
                    <input type="checkbox" checked={on} onChange={() => togglePermission(perm.code)} />
                    <span>{perm.label}</span>
                  </label>
                );
              })}
            </div>
          </div>

          <div style={{ display: "flex", gap: 8 }}>
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? "Saving..." : editingId ? "Save changes" : "Create role"}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {roles === null && !error && <p>Loading...</p>}

      {roles && roles.length > 0 && (
        <div className="card" style={{ overflow: "hidden" }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Role</th>
                <th>Can do</th>
                <th>People</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {roles.map((role) => (
                <tr key={role.id}>
                  <td>
                    <strong>{role.name}</strong>
                    {role.is_system && (
                      <span style={{ marginLeft: 8, fontSize: "0.8rem", color: "var(--ink-soft)" }}>
                        (built in)
                      </span>
                    )}
                    {role.description && (
                      <div style={{ fontSize: "0.8rem", color: "var(--ink-soft)", marginTop: 2 }}>
                        {role.description}
                      </div>
                    )}
                  </td>
                  <td>
                    {role.permissions.length === 0 ? (
                      <span style={{ color: "var(--ink-soft)" }}>Nothing yet</span>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                        {role.permissions.map((code) => {
                          const perm = role.available_permissions.find((p) => p.code === code);
                          return (
                            <span key={code} style={{ fontSize: "0.82rem" }}>
                              {perm ? perm.label : code}
                            </span>
                          );
                        })}
                      </div>
                    )}
                  </td>
                  <td className="mono">{role.staff_count}</td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <button
                      className="btn btn-secondary"
                      style={{ padding: "4px 10px", marginRight: 8 }}
                      onClick={() => startEdit(role)}
                    >
                      Edit
                    </button>
                    {!role.is_system && (
                      <button
                        className="btn btn-secondary"
                        style={{ padding: "4px 10px", color: "var(--accent-urgent)" }}
                        onClick={() => handleDelete(role)}
                      >
                        Delete
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
