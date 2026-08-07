import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { passwordResetApi } from "../api/endpoints";

/**
 * Both steps live on ONE page, switched by local state, rather than
 * two routes. With a code (as opposed to an emailed link) there's
 * nothing to navigate to -- the person never leaves this page, they
 * just switch tabs to their inbox and come back. Keeping it here also
 * means the email they typed is still in hand for step 2, instead of
 * needing to be passed through a URL.
 */
export default function ForgotPasswordPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState("request"); // "request" | "verify" | "done"
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleRequest(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await passwordResetApi.request(email);
      setStep("verify");
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleConfirm(e) {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("The two passwords don't match.");
      return;
    }

    setSubmitting(true);
    try {
      await passwordResetApi.confirm(email, code, password);
      setStep("done");
      setTimeout(() => navigate("/login", { replace: true }), 2200);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleResend() {
    setError(null);
    setCode("");
    try {
      await passwordResetApi.request(email);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: "var(--paper)" }}>
      <div style={{ padding: "20px 24px" }}>
        <Link
          to="/login"
          style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            fontSize: "0.88rem", fontWeight: 600, color: "var(--ink-soft)", textDecoration: "none",
          }}
        >
          &larr; Back to login
        </Link>
      </div>

      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
        <div className="card" style={{ width: 400, padding: 36, boxShadow: "var(--shadow-lg)" }}>
          {step === "request" && (
            <form onSubmit={handleRequest}>
              <h1 style={{ fontSize: "1.3rem", letterSpacing: "-0.01em", marginBottom: 4 }}>Forgot your password?</h1>
              <p style={{ color: "var(--ink-soft)", fontSize: "0.9rem", marginBottom: 24 }}>
                Enter your email and we'll send you a 6-digit verification code.
              </p>

              {error && <div className="error-banner">{error}</div>}

              <div className="field">
                <label htmlFor="email">Email address</label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoFocus
                  required
                />
              </div>

              <button
                type="submit"
                className="btn btn-primary"
                disabled={submitting}
                style={{ width: "100%", justifyContent: "center", padding: "11px 16px" }}
              >
                {submitting ? "Sending..." : "Send code"}
              </button>
            </form>
          )}

          {step === "verify" && (
            <form onSubmit={handleConfirm}>
              <h1 style={{ fontSize: "1.3rem", letterSpacing: "-0.01em", marginBottom: 4 }}>Enter your code</h1>
              {/* Says "if an account exists" rather than confirming one
                  does -- the backend deliberately doesn't reveal that,
                  and the UI shouldn't undo it by implying otherwise. */}
              <p style={{ color: "var(--ink-soft)", fontSize: "0.9rem", marginBottom: 24 }}>
                If an account exists for <strong>{email}</strong>, we've sent a 6-digit code.
                It expires in 10 minutes.
              </p>

              {error && <div className="error-banner">{error}</div>}

              <div className="field">
                <label htmlFor="code">Verification code</label>
                <input
                  id="code"
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="000000"
                  autoFocus
                  required
                  className="mono"
                  style={{ fontSize: "1.4rem", letterSpacing: "0.4em", textAlign: "center" }}
                />
              </div>

              <div className="field">
                <label htmlFor="password">New password</label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
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

              <div style={{ marginTop: 16, textAlign: "center", fontSize: "0.85rem" }}>
                <button
                  type="button"
                  onClick={handleResend}
                  style={{ background: "none", border: "none", color: "var(--primary)", fontWeight: 600, padding: 0 }}
                >
                  Send a new code
                </button>
              </div>
            </form>
          )}

          {step === "done" && (
            <>
              <h1 style={{ fontSize: "1.3rem", letterSpacing: "-0.01em", marginBottom: 12 }}>Password updated</h1>
              <p style={{ color: "var(--ink-soft)", fontSize: "0.92rem", margin: 0 }}>
                You can now log in with your new password. Taking you there...
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
