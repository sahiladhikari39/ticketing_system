import { useEffect, useState } from "react";
import { ticketsApi } from "../api/endpoints";
import { statusLabel } from "../utils/labels";

function formatDuration(hours) {
  if (hours === null || hours === undefined) return "—";
  if (hours < 24) return `${hours}h`;
  return `${(hours / 24).toFixed(1)}d`;
}

export default function ReportsPage() {
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    ticketsApi.reports().then(setReport).catch((err) => setError(err.message));
  }, []);

  if (error) return <div className="error-banner">{error}</div>;
  if (!report) return <p>Loading report...</p>;

  const statusEntries = Object.entries(report.status_counts);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Reports</h1>
          <p>Ticket volume, resolution speed, and per-agent workload.</p>
        </div>
      </div>

      <div style={{ display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
        <div className="card" style={{ padding: 20, flex: "1 1 160px" }}>
          <div style={{ fontSize: "1.6rem", fontWeight: 700, color: "var(--primary)" }}>{report.open_ticket_count}</div>
          <div style={{ fontSize: "0.82rem", color: "var(--ink-soft)" }}>Open / pending</div>
        </div>
        <div className="card" style={{ padding: 20, flex: "1 1 160px" }}>
          <div style={{ fontSize: "1.6rem", fontWeight: 700, color: "var(--accent-success)" }}>{report.resolved_ticket_count}</div>
          <div style={{ fontSize: "0.82rem", color: "var(--ink-soft)" }}>Resolved / closed</div>
        </div>
        <div className="card" style={{ padding: 20, flex: "1 1 160px" }}>
          <div style={{ fontSize: "1.6rem", fontWeight: 700 }} className="mono">
            {formatDuration(report.avg_resolution_hours)}
          </div>
          <div style={{ fontSize: "0.82rem", color: "var(--ink-soft)" }}>Avg. resolution time</div>
        </div>
      </div>

      <h3 style={{ fontSize: "0.95rem", marginBottom: 12 }}>By status</h3>
      <div className="card" style={{ overflow: "hidden", marginBottom: 32 }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)", textAlign: "left" }}>
              <th style={thStyle}>Status</th>
              <th style={thStyle}>Count</th>
            </tr>
          </thead>
          <tbody>
            {statusEntries.map(([status, count]) => (
              <tr key={status} style={{ borderBottom: "1px solid var(--border)" }}>
                <td style={tdStyle}>{statusLabel(status)}</td>
                <td style={tdStyle}>{count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3 style={{ fontSize: "0.95rem", marginBottom: 12 }}>Tickets handled per Support Staff</h3>
      {report.by_staff.length === 0 ? (
        <p style={{ color: "var(--ink-soft)" }}>No tickets assigned to anyone yet.</p>
      ) : (
        <div className="card" style={{ overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)", textAlign: "left" }}>
                <th style={thStyle}>Staff member</th>
                <th style={thStyle}>Assigned</th>
                <th style={thStyle}>Resolved</th>
              </tr>
            </thead>
            <tbody>
              {report.by_staff.map((row) => (
                <tr key={row.staff_id} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={tdStyle}>{row.username}</td>
                  <td style={tdStyle}>{row.assigned_count}</td>
                  <td style={tdStyle}>{row.resolved_count}</td>
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
