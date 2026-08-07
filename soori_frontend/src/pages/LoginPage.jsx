import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await login(username, password);
      // Soori Admin's ticket/reports/team/audit-log queries are all
      // deliberately empty or blocked now (they run the platform, not
      // a Client's own operations) -- sending them to the ticket
      // dashboard would just be a dead end. Clients is their actual
      // home base.
      const destination = result.user.role === "soori_admin" ? "/clients" : "/";
      navigate(destination, { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        background: "var(--paper)",
      }}
    >
      {/* Explicit way back to the landing page -- without this, anyone
          who lands here directly (a bookmark, a shared link) has no
          way to see what Soori even is before signing in. */}
      <div style={{ padding: "20px 24px" }}>
        <Link
          to="/"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontSize: "0.88rem",
            fontWeight: 600,
            color: "var(--ink-soft)",
            textDecoration: "none",
          }}
        >
          &larr; Back to home
        </Link>
      </div>

      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "24px" }}>
        <form onSubmit={handleSubmit} className="card" style={{ width: 380, padding: 36, boxShadow: "var(--shadow-lg)" }}>
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: "var(--radius-sm)",
              background: "var(--primary)",
              color: "white",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontWeight: 700,
              fontSize: "1.1rem",
              marginBottom: 20,
            }}
          >
            S
          </div>
          <h1 style={{ fontSize: "1.4rem", letterSpacing: "-0.01em", marginBottom: 4 }}>Welcome back</h1>
          <p style={{ color: "var(--ink-soft)", fontSize: "0.9rem", marginBottom: 28 }}>
            Sign in to Soori Ticketing System.
          </p>

          {error && <div className="error-banner">{error}</div>}

          <div className="field">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
              required
            />
          </div>

          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <button type="submit" className="btn btn-primary" disabled={submitting} style={{ width: "100%", justifyContent: "center", padding: "11px 16px" }}>
            {submitting ? "Signing in..." : "Sign in"}
          </button>

          <div style={{ marginTop: 16, textAlign: "center" }}>
            <Link to="/forgot-password" style={{ fontSize: "0.85rem" }}>
              Forgot your password?
            </Link>
          </div>

          <div style={{ marginTop: 8, textAlign: "center" }}>
            <Link to="/access-login" style={{ fontSize: "0.85rem", color: "var(--ink-soft)" }}>
              Have a temporary access code instead?
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
