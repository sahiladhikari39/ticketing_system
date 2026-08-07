import { useEffect, useState } from "react";
import { auditLogApi } from "../api/endpoints";
import { formatDateTime } from "../utils/format";

export default function AuditLogPage() {
  const [logs, setLogs] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    auditLogApi.list().then(setLogs).catch((err) => setError(err.message));
  }, []);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Audit log</h1>
          <p>A record of actions taken within your organization.</p>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}
      {logs === null && !error && <p>Loading...</p>}

      {logs && logs.length === 0 && (
        <div className="empty-state card">
          <h3>Nothing logged yet</h3>
          <p>Actions like reassigning a ticket will show up here.</p>
        </div>
      )}

      {logs && logs.length > 0 && (
        <div className="card" style={{ overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)", textAlign: "left" }}>
                <th style={thStyle}>Action</th>
                <th style={thStyle}>By</th>
                <th style={thStyle}>Assigned to</th>
                <th style={thStyle}>When</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={tdStyle} className="mono">{log.action}</td>
                  <td style={tdStyle}>{log.actor_username || "—"}</td>
                  <td style={tdStyle}>{log.metadata?.assigned_to_username || "—"}</td>
                  <td style={tdStyle} className="mono">{formatDateTime(log.created_at)}</td>
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
