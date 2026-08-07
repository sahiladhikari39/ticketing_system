import { useEffect, useState } from "react";
import { knowledgeBaseApi } from "../api/endpoints";

/**
 * Training material built from real service visits.
 *
 * Video leads each card rather than sitting under the text, because
 * the recording IS the training -- a written summary of a repair is a
 * reference, watching someone do it is the lesson. Everything
 * identifying the customer is stripped server-side, so what's left is
 * purely the technical content.
 */
export default function KnowledgeBasePage() {
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    knowledgeBaseApi.list().then(setEntries).catch((err) => setError(err.message));
  }, []);

  const filtered = (entries || []).filter((e) => {
    if (!query.trim()) return true;
    const haystack = [e.equipment, e.problem, e.work_performed, e.root_cause, e.parts_used]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(query.trim().toLowerCase());
  });

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Knowledge Base</h1>
          <p>
            Recordings and write-ups from real service visits. Customer details are removed —
            what's here is the repair itself.
          </p>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {entries && entries.length > 0 && (
        <div className="field" style={{ maxWidth: 380, marginBottom: 24 }}>
          <label htmlFor="kb-search">Search</label>
          <input
            id="kb-search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Fuser, paper jam, FU-2200..."
          />
        </div>
      )}

      {entries === null && !error && <p>Loading...</p>}

      {entries && entries.length === 0 && (
        <div className="empty-state card">
          <h3>Nothing here yet</h3>
          <p>
            When an engineer files a service report, they can tick "add to the Knowledge Base"
            and it'll appear here for the team to learn from.
          </p>
        </div>
      )}

      {entries && entries.length > 0 && filtered.length === 0 && (
        <div className="empty-state card">
          <h3>No matches for "{query}"</h3>
          <p>Try a different part name, fault, or piece of equipment.</p>
        </div>
      )}

      {filtered.length > 0 && (
        <div className="kb-grid">
          {filtered.map((entry) => (
            <article key={entry.id} className="kb-card">
              {entry.service_video_url ? (
                <video src={entry.service_video_url} controls preload="metadata" />
              ) : (
                <div className="kb-no-video">Write-up only — no recording</div>
              )}
              <div className="kb-card-body">
                {entry.equipment && <div className="kb-card-equipment">{entry.equipment}</div>}
                <h3 className="kb-card-problem">{entry.problem}</h3>

                {entry.root_cause && (
                  <p className="kb-field" style={{ margin: 0 }}>
                    <span className="kb-field-label">Cause: </span>
                    {entry.root_cause}
                  </p>
                )}
                {entry.work_performed && (
                  <p className="kb-field" style={{ margin: 0 }}>
                    <span className="kb-field-label">Fix: </span>
                    {entry.work_performed}
                  </p>
                )}
                {entry.parts_used && (
                  <p className="kb-field mono" style={{ margin: 0, fontSize: "0.8rem", color: "var(--ink-soft)" }}>
                    {entry.parts_used}
                  </p>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  );
}
