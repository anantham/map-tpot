export default function PublishedProfileStatus({ source }) {
  if (!source || source.status === 'not_present') return null
  const current = source.status === 'available'
  const messages = {
    unavailable: 'Archive package profiles are hidden because current publication could not be checked.',
    unchecked: 'Archive package profiles are hidden until current publication is checked.',
    withdrawn: 'Archive package profiles are hidden because the publisher withdrew this package.',
    superseded: 'The saved Archive profile package no longer matches the current publication. Its profiles are hidden until refreshed.',
    partial: 'Some saved Archive profiles are hidden because they no longer match current publication or eligibility.',
  }
  return <aside className="research-notes-preview-warning" aria-label="Archive profile source status">
    <p>{current ? 'Archive package profiles checked against current publication.' : messages[source.status] || 'Archive profile source is unavailable.'}</p>
    {Number.isInteger(source.visibleProfileObservations) && <small>
      {source.visibleProfileObservations.toLocaleString()} visible profile observations
      {source.hiddenProfileObservations > 0 ? ` · ${source.hiddenProfileObservations.toLocaleString()} hidden` : ''}.
    </small>}
    {source.exportId && <small>Publication: {source.exportId}.</small>}
    {source.checkedAt && <small>Checked {new Date(source.checkedAt).toLocaleString()}.</small>}
    {!current && <small>Independent saved sources remain available. A hidden source is not evidence of no match.</small>}
    <small>Publication eligibility is not a verification of profile claims or current contactability.</small>
  </aside>
}
