/**
 * A file input that fits whatever width it's given.
 *
 * The native <input type="file"> renders its own "No file chosen"
 * text, and that text doesn't wrap or truncate -- in a narrow column
 * it runs straight past the edge of its container. This hides the
 * native input entirely (still fully functional, just visually
 * invisible) and renders a button + filename we control completely,
 * so the filename can be truncated with an ellipsis instead of
 * overflowing.
 */
export default function FileInput({ id, accept, onChange, fileName, placeholder = "No file chosen" }) {
  return (
    <div className="file-input">
      <input
        id={id}
        type="file"
        accept={accept}
        onChange={(e) => onChange(e.target.files?.[0] || null)}
        className="file-input-native"
      />
      <label htmlFor={id} className="file-input-button">
        Choose file
      </label>
      <span className="file-input-name" title={fileName || ""}>
        {fileName || placeholder}
      </span>
    </div>
  );
}
