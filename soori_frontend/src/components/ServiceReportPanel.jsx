import { useState } from "react";
import { serviceReportsApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { formatDateTime } from "../utils/format";
import FileInput from "./FileInput";
import { validateVideoDuration, MAX_SERVICE_VIDEO_SECONDS } from "../utils/video";
import { validateFileSize, formatBytes } from "../utils/filesize";

const MAX_SERVICE_VIDEO_BYTES = 2 * 1024 * 1024 * 1024; // 2GB -- see ServiceReportSerializer for why

const EMPTY_DRAFT = {
  work_performed: "",
  root_cause: "",
  parts_used: "",
  internal_notes: "",
  service_video: null,
  video_title: "",
};

/**
 * The service report on a ticket, rendered differently for each
 * audience because they genuinely see different documents:
 *
 *   Customer  -- only the released summary, or a plain "not yet" note.
 *   Engineer  -- writes the internal record; can't touch the summary.
 *   Service layer -- reads everything, writes the summary, releases it.
 *
 * The internal and customer-facing halves are visually separated
 * (warm edge vs green edge) using the same colours the rest of the app
 * already uses for "staff only" and "shared" -- so the distinction is
 * learned once, not per screen.
 */
export default function ServiceReportPanel({ ticket, report, onChanged }) {
  const { user } = useAuth();
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  // A basic starting point rather than a blank field every time -- staff
  // still reviews and can rewrite it entirely before sending; this
  // doesn't skip that step, it just means there's usually something
  // to edit rather than compose from nothing. Only used when no
  // summary has been written yet; once one exists, that's shown as-is.
  const suggestedSummary = report
    ? `We attended your reported issue ("${ticket.title}") and completed the necessary work. ` +
      `If anything doesn't seem right, please reply on this ticket and we'll take another look.`
    : "";
  const [summary, setSummary] = useState(report?.customer_summary || suggestedSummary);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [checkingVideo, setCheckingVideo] = useState(false);
  // Once the engineer edits the title directly, stop overwriting it
  // with whatever they type in "what you did on site".
  const [titleTouched, setTitleTouched] = useState(false);

  const isCustomer = user.role === "sub_client";
  const permissions = user.staff_permissions || [];
  // Two DIFFERENT jobs, not one "staff can write" bucket. Filing the
  // initial report is the assigned engineer's job -- someone who was
  // never on site has nothing to fill in there. Approving/summarising
  // is the Service Department's job. Client Admin holds every
  // permission implicitly (see User.has_staff_perm on the backend),
  // so this reads correctly for them too without a special case.
  const canFileReport = !isCustomer && permissions.includes("service_report.write");
  const canApprove = !isCustomer && permissions.includes("service_report.approve");

  function set(field, value) {
    setDraft((d) => {
      const next = { ...d, [field]: value };
      // "What you did on site" becomes the video title by default --
      // this is what makes a recording findable later in the
      // Knowledge Base ("IMG_0042.mp4" tells an intern nothing).
      // Stops once the engineer edits the title themselves.
      if (field === "work_performed" && !titleTouched) {
        next.video_title = value;
      }
      return next;
    });
  }

  function handleTitleEdit(value) {
    setTitleTouched(true);
    set("video_title", value);
  }

  async function handleVideoChange(file) {
    setError(null);
    if (!file) {
      set("service_video", null);
      return;
    }
    const sizeProblem = validateFileSize(file, MAX_SERVICE_VIDEO_BYTES, "Recording");
    if (sizeProblem) {
      setError(sizeProblem);
      return;
    }
    setCheckingVideo(true);
    const durationProblem = await validateVideoDuration(file, MAX_SERVICE_VIDEO_SECONDS);
    setCheckingVideo(false);
    if (durationProblem) {
      setError(durationProblem);
      return;
    }
    set("service_video", file);
  }

  async function handleCreate(e) {
    e.preventDefault();
    setError(null);
    // Required, not optional -- the recording IS the training
    // material this whole feature exists for. Checked here too (not
    // just server-side) so the person sees why immediately rather
    // than after a round trip.
    if (!draft.service_video) {
      setError("A recording of the visit is required to file a report.");
      return;
    }
    setBusy(true);
    try {
      await serviceReportsApi.create({ ticket: ticket.id, ...draft });
      setDraft(EMPTY_DRAFT);
      setTitleTouched(false);
      onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveSummary(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await serviceReportsApi.update(report.id, { customer_summary: summary });
      onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRelease() {
    if (!window.confirm("Send this summary to the customer? They'll be emailed that it's ready.")) return;
    setError(null);
    setBusy(true);
    try {
      // Whatever's currently in the box gets saved FIRST, then
      // released, as one action. Before this fix, clicking "Send"
      // without a separate "Save draft" click first meant the backend
      // still had an empty customer_summary -- so release correctly
      // refused, but from the box visibly having text, that read as a
      // confusing false rejection rather than the real cause.
      await serviceReportsApi.update(report.id, { customer_summary: summary });
      await serviceReportsApi.releaseToCustomer(report.id);
      onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleKnowledgeBase() {
    setError(null);
    try {
      await serviceReportsApi.update(report.id, {
        include_in_knowledge_base: !report.include_in_knowledge_base,
      });
      onChanged();
    } catch (err) {
      setError(err.message);
    }
  }

  // ---- Customer view -------------------------------------------------
  if (isCustomer) {
    if (!report || !report.customer_summary) {
      return (
        <div className="card" style={{ padding: 24 }}>
          <p className="section-label">Service report</p>
          <p style={{ color: "var(--ink-soft)", fontSize: "0.9rem", margin: 0 }}>
            Nothing yet. Once an engineer has attended and the visit has been reviewed,
            your report will appear here.
          </p>
        </div>
      );
    }
    // Styled like an actual document -- a title block, then the body --
    // rather than a plain paragraph sitting in a coloured box. This is
    // the one document a customer receives about their own ticket, so
    // it reads like a report, not a chat message.
    return (
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div style={{ padding: "24px 28px", borderBottom: "1px solid var(--border)", background: "var(--paper)" }}>
          <div className="section-label" style={{ marginBottom: 6 }}>Service report</div>
          <h2 style={{ margin: 0, fontSize: "1.15rem", letterSpacing: "-0.01em" }}>{ticket.title}</h2>
          <p style={{ margin: "4px 0 0", fontSize: "0.8rem", color: "var(--ink-soft)" }}>
            Completed {formatDateTime(report.shared_with_customer_at)}
          </p>
        </div>
        <div style={{ padding: "24px 28px" }}>
          <p style={{ margin: 0, fontSize: "0.98rem", lineHeight: 1.7 }}>{report.customer_summary}</p>
        </div>
      </div>
    );
  }

  // ---- No report yet: engineer writes one, everyone else waits -------
  if (!report) {
    // The Service Manager/Department was never on site -- showing them
    // the engineer's blank filing form made no sense and looked like a
    // stray, unexplained card. They get a simple waiting state instead;
    // only someone who can actually FILE a report sees the form.
    if (!canFileReport) {
      return (
        <div className="card" style={{ padding: 24 }}>
          <p className="section-label">Service report</p>
          <p style={{ color: "var(--ink-soft)", fontSize: "0.9rem", margin: 0 }}>
            No report has been filed yet. It'll appear here once the assigned engineer submits one.
          </p>
        </div>
      );
    }
    return (
      <div className="card" style={{ padding: 24 }}>
        <p className="section-label">Service report</p>
        {error && <div className="error-banner">{error}</div>}
        <p className="zone-note">
          Recorded after attending the site. Everything here stays inside your organisation —
          the customer only ever sees a short summary, written separately once this is reviewed.
        </p>

        <form onSubmit={handleCreate}>
          <div className="zone-internal" style={{ marginBottom: 18 }}>
            <div className="field">
              <label htmlFor="work">What you did on site</label>
              <textarea
                id="work"
                value={draft.work_performed}
                onChange={(e) => set("work_performed", e.target.value)}
                placeholder="Replaced the fuser unit, cleaned the paper path, ran a 200-page test."
                required
              />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <div className="field">
                <label htmlFor="cause">Root cause</label>
                <input
                  id="cause"
                  value={draft.root_cause}
                  onChange={(e) => set("root_cause", e.target.value)}
                  placeholder="Paper dust buildup"
                />
              </div>
              <div className="field">
                <label htmlFor="parts">Parts used</label>
                <input
                  id="parts"
                  value={draft.parts_used}
                  onChange={(e) => set("parts_used", e.target.value)}
                  placeholder="Fuser unit FU-2200 x1"
                />
              </div>
            </div>
            <div className="field">
              <label htmlFor="notes">Internal notes</label>
              <textarea
                id="notes"
                value={draft.internal_notes}
                onChange={(e) => set("internal_notes", e.target.value)}
                placeholder="Anything your team should know. Never shown to the customer."
              />
            </div>
            <div className="field">
              <label htmlFor="video-title">Recording title</label>
              <input
                id="video-title"
                value={draft.video_title}
                onChange={(e) => handleTitleEdit(e.target.value)}
                placeholder="Filled in from \u201cwhat you did on site\u201d until you edit it"
                required
              />
            </div>
            <div className="field">
              <label htmlFor="video">On-site recording</label>
              <FileInput
                id="video"
                accept="video/*"
                fileName={draft.service_video?.name}
                onChange={handleVideoChange}
                placeholder={checkingVideo ? "Checking length..." : "No file chosen"}
              />
              <span style={{ fontSize: "0.76rem", color: "var(--ink-soft)" }}>
                Required. Up to {formatBytes(MAX_SERVICE_VIDEO_BYTES)}, {Math.round(MAX_SERVICE_VIDEO_SECONDS / 60)} minutes max.
                Internal only \u2014 used for training, never sent to the customer. Automatically
                added to the Knowledge Base; the service team can remove it from there afterwards if needed.
              </span>
            </div>
          </div>

          <button type="submit" className="btn btn-primary" disabled={busy || checkingVideo}>
            {busy ? "Saving..." : "Save service report"}
          </button>
        </form>
      </div>
    );
  }

  // ---- Report exists: staff view ------------------------------------
  return (
    <div className="card" style={{ padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
        <p className="section-label" style={{ flex: 1 }}>Service report</p>
        <span style={{ fontSize: "0.85rem", color: "var(--ink-soft)" }}>
          {report.is_shared_with_customer ? "Shared with customer" : "Not yet shared"}
        </span>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="zone-internal" style={{ marginBottom: 20 }}>
        <p className="zone-note" style={{ marginBottom: 12, fontWeight: 600 }}>
          Internal record — never sent to the customer
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <ReportField label="What was done" value={report.work_performed} />
          <ReportField label="Root cause" value={report.root_cause} />
          <ReportField label="Parts used" value={report.parts_used} />
          <ReportField label="Internal notes" value={report.internal_notes} />
        </div>

        {report.service_video_url && (
          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--ink-soft)", marginBottom: 6 }}>
              On-site recording
            </div>
            <video
              src={report.service_video_url}
              controls
              preload="metadata"
              style={{
                width: "100%", maxWidth: 480, borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border)", background: "#000",
              }}
            />
          </div>
        )}

        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.85rem", marginTop: 16 }}>
          <input
            type="checkbox"
            checked={report.include_in_knowledge_base}
            onChange={handleToggleKnowledgeBase}
          />
          Available in the Knowledge Base as training material
        </label>
      </div>

      {/* Only someone with approval rights can write or release the
          customer-facing wording, matching the backend rule. */}
      {canApprove ? (
        <form onSubmit={handleSaveSummary}>
          <div className="zone-customer">
            <p className="zone-note" style={{ marginBottom: 12, fontWeight: 600 }}>
              Customer summary — this is all the customer will see
            </p>
            <div className="field" style={{ marginBottom: 12 }}>
              <textarea
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                placeholder="Plain language, no internal detail. e.g. We replaced the fuser unit and tested the printer. It's working normally again."
                disabled={report.is_shared_with_customer}
              />
              {!report.customer_summary && !report.is_shared_with_customer && (
                <span style={{ fontSize: "0.76rem", color: "var(--ink-soft)" }}>
                  Suggested starting point &mdash; review and edit before sending.
                </span>
              )}
            </div>

            {report.is_shared_with_customer ? (
              <p style={{ fontSize: "0.8rem", color: "var(--ink-soft)", margin: 0 }}>
                Sent {formatDateTime(report.shared_with_customer_at)}
                {report.summarised_by_username ? ` by ${report.summarised_by_username}` : ""}.
              </p>
            ) : (
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button type="submit" className="btn btn-secondary" disabled={busy}>
                  Save draft
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleRelease}
                  disabled={busy || !summary.trim()}
                >
                  Send to customer
                </button>
              </div>
            )}
          </div>
        </form>
      ) : (
        <div className="zone-customer">
          <p className="zone-note" style={{ margin: 0 }}>
            {report.customer_summary
              ? `Summary prepared: "${report.customer_summary}"`
              : "No customer summary written yet. Your role can't write or send it."}
          </p>
        </div>
      )}
    </div>
  );
}

function ReportField({ label, value }) {
  if (!value) return null;
  return (
    <div>
      <div style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--ink-soft)" }}>{label}</div>
      <div style={{ fontSize: "0.92rem", lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{value}</div>
    </div>
  );
}
