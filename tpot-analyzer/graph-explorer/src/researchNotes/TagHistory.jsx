const polarityLabel = (polarity) => (polarity === 1 ? 'IN' : polarity === -1 ? 'NOT IN' : '—')

export default function TagHistory({ events = [] }) {
  return (
    <details className="tag-history">
      <summary>Recent changes ({events.length})</summary>
      {events.length === 0 ? <p>No changes yet.</p> : <ol>
        {events.map((event) => (
          <li key={event.event_id}>
            {event.action === 'remove'
              ? `Removed ${event.tag}`
              : `Set ${event.tag} · ${polarityLabel(event.polarity)}`}
            {event.recorded_at ? ` · ${event.recorded_at}` : ''}
            {event.source ? ` · ${event.source.replaceAll('_', ' ')}` : ''}
            {event.evidence_binding_status
              ? ` · evidence ${event.evidence_binding_status.replaceAll('_', ' ')}`
              : ''}
          </li>
        ))}
      </ol>}
    </details>
  )
}
