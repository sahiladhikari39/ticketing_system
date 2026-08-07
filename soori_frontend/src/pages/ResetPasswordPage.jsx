import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { passwordResetApi } from "../api/endpoints";

export default function ResetPasswordPage() {
  // uid and token come straight out of the URL the email linked to --
  // together they stand in for being logged in, which the person
  // obviously can't be at this point.
  const { uid, token } = useParams();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("The two passwords don't match.");
      return;
    }

    setSubmitting(true);
    try {
      await passwordResetApi.confirm(uid, token, password);
      setDone(true);
      // Brief pause so the success message is actually readable before
      // the page changes out from under them.
      setTimeout(() => navigate("/login", { replace: true }), 2200);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--paper)", padding: 24 }}>
      <div className="card" style={{ width: 380, padding: 36, boxShadow: "var(--shadow-lg)" }}>
        {done ? (
          <>
            <h1 style={{ fontSize: "1.3rem", letterSpacing: "-0.01em", marginBottom: 12 }}>Password updated</h1>
            <p style={{ color: "var(--ink-soft)", fontSize: "0.92rem", marginBottom: 0 }}>
              You can now log in with your new password. Taking you there...
            </p>
          </>
        ) : (
          <form onSubmit={handleSubmit}>
            <h1 style={{ fontSize: "1.3rem", letterSpacing: "-0.01em", marginBottom: 4 }}>Choose a new password</h1>
            <p style={{ color: "var(--ink-soft)", fontSize: "0.9rem", marginBottom: 24 }}>
              Pick something you haven't used before.
            </p>

            {error && <div className="error-banner">{error}</div>}

            <div className="field">
              <label htmlFor="password">New password</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoFocus
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
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting}
              style={{ width: "100%", justifyContent: "center", padding: "11px 16px" }}
            >
              {submitting ? "Updating..." : "Set new password"}
            </button>

            <div style={{ marginTop: 16, textAlign: "center" }}>
              <Link to="/forgot-password" style={{ fontSize: "0.85rem" }}>
                Link expired? Request a new one
              </Link>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
