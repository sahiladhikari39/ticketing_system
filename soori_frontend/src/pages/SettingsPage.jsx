import { useState } from "react";
import { meApi } from "../api/endpoints";

export default function SettingsPage() {
  const [form, setForm] = useState({ current_password: "", new_password: "", confirm_password: "" });
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
    setSuccess(false);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSuccess(false);

    if (form.new_password !== form.confirm_password) {
      setError("New password and confirmation don't match.");
      return;
    }

    setSubmitting(true);
    try {
      await meApi.changePassword({
        current_password: form.current_password,
        new_password: form.new_password,
      });
      setForm({ current_password: "", new_password: "", confirm_password: "" });
      setSuccess(true);
    } catch (err) {
      // The backend's password validators return field-specific
      // messages (e.g. "too common", "too short") -- apiFetch already
      // extracts a readable `detail` from whatever shape the error
      // response takes, so this just displays it directly.
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <h1>Account settings</h1>
      </div>

      <form onSubmit={handleSubmit} className="card" style={{ padding: 24, maxWidth: 420 }}>
        <h3 style={{ fontSize: "0.95rem", marginTop: 0 }}>Change password</h3>

        {error && <div className="error-banner">{error}</div>}
        {success && (
          <div className="card" style={{ padding: 12, marginBottom: 16, background: "var(--accent-success-soft)", color: "var(--accent-success)", fontSize: "0.88rem" }}>
            Password changed successfully.
          </div>
        )}

        <div className="field">
          <label htmlFor="current">Current password</label>
          <input
            id="current"
            type="password"
            value={form.current_password}
            onChange={(e) => update("current_password", e.target.value)}
            required
          />
        </div>

        <div className="field">
          <label htmlFor="new">New password</label>
          <input
            id="new"
            type="password"
            value={form.new_password}
            onChange={(e) => update("new_password", e.target.value)}
            required
          />
          <span style={{ fontSize: "0.78rem", color: "var(--ink-soft)" }}>
            At least 10 characters, not something easily guessed.
          </span>
        </div>

        <div className="field">
          <label htmlFor="confirm">Confirm new password</label>
          <input
            id="confirm"
            type="password"
            value={form.confirm_password}
            onChange={(e) => update("confirm_password", e.target.value)}
            required
          />
        </div>

        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? "Changing..." : "Change password"}
        </button>
      </form>
    </>
  );
}
