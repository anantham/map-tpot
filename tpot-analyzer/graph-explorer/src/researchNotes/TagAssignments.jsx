const groupCopy = {
  in: {
    empty: 'Nothing included yet.',
    label: 'IN',
    polarity: 1,
  },
  notIn: {
    empty: 'Nothing excluded yet.',
    label: 'NOT IN',
    polarity: -1,
  },
}

function AssignmentGroup({ disabled, group, onRemove, onSelect, tags }) {
  const items = tags.filter((tag) => tag.polarity === group.polarity)
  const regionLabel = `${group.label} tags (${items.length})`
  return (
    <section
      className={`tag-assignment-group ${group.polarity === 1 ? 'is-in' : 'is-not-in'}`}
      aria-label={regionLabel}
    >
      <header>
        <strong>{group.label}</strong>
        <span>{items.length}</span>
      </header>
      {items.length === 0 && <p>{group.empty}</p>}
      {items.map((item) => (
        <article key={`${item.tag}-${item.polarity}`}>
          <button
            type="button"
            className="tag-assignment-name"
            onClick={() => onSelect?.(item.tag)}
          >
            {item.tag}
          </button>
          <button
            type="button"
            className="tag-assignment-remove"
            aria-label={`Retract ${item.tag} judgment from ${group.label}`}
            disabled={disabled}
            onClick={() => onRemove?.(item.tag)}
          >
            Retract
          </button>
        </article>
      ))}
    </section>
  )
}

export default function TagAssignments(props) {
  return (
    <div className="tag-assignments" aria-label="Current tag judgments">
      <AssignmentGroup {...props} group={groupCopy.in} />
      <AssignmentGroup {...props} group={groupCopy.notIn} />
    </div>
  )
}
