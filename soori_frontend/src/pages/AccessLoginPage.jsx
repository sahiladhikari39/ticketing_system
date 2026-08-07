import { useState } from "react";
import { Link } from "react-router-dom";
import { accessCodesApi } from "../api/endpoints";

/**
 * For someone with a temporary code and NO real account -- an intern,
 * or an engineer approved for a customer's history. This is a
 * completely separate flow from /login: there's no JWT, no session,
 * nothing stored. Every visit here starts fresh; closing the tab and
 * coming back means entering the code again. That's deliberate --
 * this credential expires on its own, and nothing here should outlive
 * that by holding onto a session the way a real login would.
 */
export default function AccessLoginPage() {
  const [username, setUsername] = useState("");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const data = await accessCodesApi.login(username.trim(), secret.trim());
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (result) {
    return <AccessResultView data={result} onBack={() => setResult(null)} />;
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: "var(--paper)" }}>
      <div style={{ padding: "20px 24px" }}>
        <Link
          to="/"
          style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            fontSize: "0.88rem", fontWeight: 600, color: "var(--ink-soft)", textDecoration: "none",
          }}
        >
          &larr; Back to home
        </Link>
      </div>

      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
        <form onSubmit={handleSubmit} className="card" style={{ width: 400, padding: 36, boxShadow: "var(--shadow-lg)" }}>
          <h1 style={{ fontSize: "1.3rem", letterSpacing: "-0.01em", marginBottom: 4 }}>Enter your access code</h1>
          <p style={{ color: "var(--ink-soft)", fontSize: "0.9rem", marginBottom: 24 }}>
            For a temporary code someone gave you \u2014 not your everyday Soori login.
          </p>

          {error && <div className="error-banner">{error}</div>}

          <div className="field">
            <label htmlFor="ac-username">Username</label>
            <input
              id="ac-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. knowledge-a1b2c3"
              autoFocus
              required
            />
          </div>

          <div className="field">
            <label htmlFor="ac-secret">Code</label>
            <input
              id="ac-secret"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder="XXXX-XXXX-XXXX"
              className="mono"
              required
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            disabled={submitting}
            style={{ width: "100%", justifyContent: "center", padding: "11px 16px" }}
          >
            {submitting ? "Checking..." : "Continue"}
          </button>

          <div style={{ marginTop: 16, textAlign: "center" }}>
            <Link to="/login" style={{ fontSize: "0.85rem" }}>
              Have a regular account instead?
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}

function AccessResultView({ data, onBack }) {
  const isKnowledgeBase = data.scope === "knowledge_base";
  const title = isKnowledgeBase ? "Knowledge Base" : "Service history";
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");

  function runSearch(e) {
    e.preventDefault();
    setAppliedQuery(query.trim().toLowerCase());
  }

  const filteredEntries = !isKnowledgeBase || !appliedQuery
    ? data.entries
    : data.entries.filter((entry) => {
        const haystack = [entry.video_title, entry.problem, entry.equipment, entry.work_performed, entry.root_cause, entry.parts_used]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return haystack.includes(appliedQuery);
      });

  return (
    <div style={{ minHeight: "100vh", background: "var(--paper)" }}>
      <header style={{ padding: "20px 24px", borderBottom: "1px solid var(--border)", background: "var(--surface)" }}>
        <div style={{ maxWidth: 1000, margin: "0 auto", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontWeight: 700 }}>{data.label}</div>
            <div style={{ fontSize: "0.8rem", color: "var(--ink-soft)" }}>
              {title}
              {data.customer && ` \u00b7 ${data.customer}`}
              {" \u00b7 expires "}
              {new Date(data.expires_at).toLocaleString()}
            </div>
          </div>
          <button className="btn btn-secondary" onClick={onBack}>Log out of this code</button>
        </div>
      </header>

      <main style={{ maxWidth: 1000, margin: "0 auto", padding: 32 }}>
        {isKnowledgeBase && data.entries.length > 0 && (
          <form onSubmit={runSearch} style={{ display: "flex", gap: 8, marginBottom: 24, maxWidth: 460 }}>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Fuser, paper jam, FU-2200..."
              style={{
                flex: 1, padding: "9px 12px", border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)", fontSize: "0.92rem",
              }}
            />
            <button type="submit" className="btn btn-primary">Search</button>
            {appliedQuery && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => { setQuery(""); setAppliedQuery(""); }}
              >
                Clear
              </button>
            )}
          </form>
        )}

        {data.entries.length === 0 ? (
          <div className="empty-state card">
            <h3>Nothing here yet</h3>
            <p>There's no material available for this code right now.</p>
          </div>
        ) : isKnowledgeBase && filteredEntries.length === 0 ? (
          <div className="empty-state card">
            <h3>No matches for "{query}"</h3>
            <p>Try a different part name, fault, or piece of equipment.</p>
          </div>
        ) : isKnowledgeBase ? (
          <div className="kb-grid">
            {filteredEntries.map((entry) => (
              <article key={entry.id} className="kb-card">
                {entry.service_video_url ? (
                  <video src={entry.service_video_url} controls preload="metadata" />
                ) : (
                  <div className="kb-no-video">Write-up only \u2014 no recording</div>
                )}
                <div className="kb-card-body">
                  {entry.equipment && <div className="kb-card-equipment">{entry.equipment}</div>}
                  <h3 className="kb-card-problem">{entry.video_title || entry.problem}</h3>
                  {entry.root_cause && (
                    <p className="kb-field" style={{ margin: 0 }}>
                      <span className="kb-field-label">Cause: </span>{entry.root_cause}
                    </p>
                  )}
                  {entry.work_performed && (
                    <p className="kb-field" style={{ margin: 0 }}>
                      <span className="kb-field-label">Fix: </span>{entry.work_performed}
                    </p>
                  )}
                </div>
              </article>
            ))}
          </div>
        ) : data.scope === "engineer_history" ? (
          // Full detail, laid out like an actual report -- the whole
          // point of this access is preparing for a repeat job, which
          // a cramped table row of paragraph text didn't serve well.
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {data.entries.map((entry) => (
              <div key={entry.id} className="card" style={{ padding: 0, overflow: "hidden" }}>
                <div style={{ padding: "18px 22px", borderBottom: "1px solid var(--border)", background: "var(--paper)" }}>
                  {entry.equipment && (
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.72rem", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--primary)" }}>
                      {entry.equipment}
                    </div>
                  )}
                  <h3 style={{ margin: "2px 0 0", fontSize: "1.05rem" }}>{entry.problem}</h3>
                  <div style={{ fontSize: "0.8rem", color: "var(--ink-soft)", marginTop: 4 }}>
                    {entry.engineer_username && `Attended by ${entry.engineer_username} \u00b7 `}
                    {new Date(entry.created_at).toLocaleDateString()}
                  </div>
                </div>
                <div style={{ padding: "18px 22px", display: "flex", flexDirection: "column", gap: 14 }}>
                  <DetailField label="What was done" value={entry.work_performed} />
                  <DetailField label="Root cause" value={entry.root_cause} />
                  <DetailField label="Parts used" value={entry.parts_used} />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="card" style={{ overflow: "hidden" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Equipment</th>
                  <th>Problem</th>
                  <th>Summary</th>
                </tr>
              </thead>
              <tbody>
                {data.entries.map((entry) => (
                  <tr key={entry.id}>
                    <td>{entry.equipment || "\u2014"}</td>
                    <td>{entry.problem}</td>
                    <td>{entry.customer_summary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}

function DetailField({ label, value }) {
  if (!value) return null;
  return (
    <div>
      <div style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--ink-soft)" }}>{label}</div>
      <div style={{ fontSize: "0.92rem", lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{value}</div>
    </div>
  );
}
