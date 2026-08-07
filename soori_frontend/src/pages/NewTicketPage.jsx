import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ticketsApi } from "../api/endpoints";
import FileInput from "../components/FileInput";
import { validateVideoDuration, MAX_TICKET_VIDEO_SECONDS } from "../utils/video";
import { validateFileSize, formatBytes } from "../utils/filesize";

const MAX_ATTACHMENT_BYTES = 2 * 1024 * 1024;
const MAX_VIDEO_BYTES = 5 * 1024 * 1024;

// Common issues for a printer/electronics service business -- picking
// one of these gives Service Department a consistent, searchable title
// instead of every customer describing the same fault differently.
// "Something else" drops to a free-text field for anything that
// doesn't fit.
const STANDARD_TITLES = [
  "Printer not turning on",
  "Paper jam",
  "Print quality issue (streaks, faded, or blank pages)",
  "Printer not connecting to network or Wi-Fi",
  "Toner or ink cartridge not recognized",
  "Frequent paper misfeeds",
  "Display or control panel not responding",
  "Unusual noise during printing",
  "Software or driver installation issue",
];

const OTHER = "__other__";

export default function NewTicketPage() {
  const navigate = useNavigate();
  const [titleChoice, setTitleChoice] = useState("");
  const [customTitle, setCustomTitle] = useState("");
  const [form, setForm] = useState({
    description: "",
    product_or_service: "",
    priority: "medium",
    attachment: null,
    video: null,
  });
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [checkingVideo, setCheckingVideo] = useState(false);

  const title = titleChoice === OTHER ? customTitle : titleChoice;

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  function handleAttachmentChange(file) {
    setError(null);
    const problem = validateFileSize(file, MAX_ATTACHMENT_BYTES, "File");
    if (problem) {
      setError(problem);
      update("attachment", null);
      return;
    }
    update("attachment", file);
  }

  async function handleVideoChange(file) {
    setError(null);
    if (!file) {
      update("video", null);
      return;
    }
    const sizeProblem = validateFileSize(file, MAX_VIDEO_BYTES, "Video");
    if (sizeProblem) {
      setError(sizeProblem);
      update("video", null);
      return;
    }
    setCheckingVideo(true);
    const durationProblem = await validateVideoDuration(file, MAX_TICKET_VIDEO_SECONDS);
    setCheckingVideo(false);
    if (durationProblem) {
      setError(durationProblem);
      update("video", null);
      return;
    }
    update("video", file);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      // Note: there's no `client` field here at all -- the backend
      // derives it automatically from whoever's logged in
      // (perform_create on TicketViewSet). There's nothing to spoof
      // because there's nothing to send.
      const ticket = await ticketsApi.create({ ...form, title });
      navigate(`/tickets/${ticket.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <h1>New ticket</h1>
      </div>

      <form onSubmit={handleSubmit} className="card" style={{ padding: 28, maxWidth: 720 }}>
        {error && <div className="error-banner">{error}</div>}

        <div className="field">
          <label htmlFor="title-choice">What's the problem</label>
          <select
            id="title-choice"
            value={titleChoice}
            onChange={(e) => setTitleChoice(e.target.value)}
            required
          >
            <option value="" disabled>Select the closest match...</option>
            {STANDARD_TITLES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
            <option value={OTHER}>Something else</option>
          </select>
        </div>

        {titleChoice === OTHER && (
          <div className="field">
            <label htmlFor="custom-title">Describe it in a few words</label>
            <input
              id="custom-title"
              value={customTitle}
              onChange={(e) => setCustomTitle(e.target.value)}
              required
            />
          </div>
        )}

        <div className="field">
          <label htmlFor="description">Description</label>
          <textarea
            id="description"
            value={form.description}
            onChange={(e) => update("description", e.target.value)}
            required
          />
        </div>

        <div className="field">
          <label htmlFor="product">Product / service</label>
          <input
            id="product"
            value={form.product_or_service}
            onChange={(e) => update("product_or_service", e.target.value)}
            placeholder="e.g. Acme Web App"
          />
        </div>

        <div className="field">
          <label htmlFor="priority">Priority</label>
          <select id="priority" value={form.priority} onChange={(e) => update("priority", e.target.value)}>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="urgent">Urgent</option>
          </select>
        </div>

        <div className="section-label" style={{ marginTop: 28 }}>Attach evidence (optional)</div>
        <p style={{ fontSize: "0.82rem", color: "var(--ink-soft)", marginTop: -6, marginBottom: 16 }}>
          A photo or a short clip of the problem helps the engineer arrive prepared.
          You can add these now — afterwards the ticket becomes a conversation.
        </p>

        <div className="upload-row">
          <div className="field">
            <label htmlFor="attachment">Photo or document</label>
            <FileInput
              id="attachment"
              fileName={form.attachment?.name}
              onChange={handleAttachmentChange}
            />
            <span className="field-hint">Up to {formatBytes(MAX_ATTACHMENT_BYTES)}</span>
          </div>
          <div className="field">
            <label htmlFor="video">Video</label>
            <FileInput
              id="video"
              accept="video/*"
              fileName={form.video?.name}
              onChange={handleVideoChange}
              placeholder={checkingVideo ? "Checking length..." : "No file chosen"}
            />
            <span className="field-hint">
              Up to {formatBytes(MAX_VIDEO_BYTES)}, {MAX_TICKET_VIDEO_SECONDS} seconds max
            </span>
          </div>
        </div>

        <button type="submit" className="btn btn-primary" disabled={submitting || checkingVideo || !title} style={{ marginTop: 8 }}>
          {submitting ? "Submitting..." : "Submit ticket"}
        </button>
      </form>
    </>
  );
}
