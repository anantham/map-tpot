export default function StoredPostText({ text, createdAt, capturedAt, sourceLabel }) {
  if (typeof text !== 'string' || !text.trim()) {
    return <small>Stored post text is unavailable in this response.</small>
  }
  return <details>
    <summary>Read stored post text</summary>
    <section aria-label="Stored post text">
      <small>{sourceLabel}. This is all text retained in this field; the capture itself may already be truncated.</small>
      <p className="stored-post-text">{text}</p>
      <small>Post date as reported: {createdAt || 'unknown'}</small>
      <small>Capture time: {capturedAt || 'not recorded in this response'}</small>
    </section>
  </details>
}
