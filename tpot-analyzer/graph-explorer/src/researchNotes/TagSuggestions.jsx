function proposalPolarity(suggestion) {
  if (suggestion?.polarity === 'in') return 'in'
  if (['out', 'not_in'].includes(suggestion?.polarity)) return 'not_in'
  return null
}

function proposalQuote(suggestion) {
  return suggestion?.sourceQuote || suggestion?.quote || ''
}

function proposalKind(suggestion) {
  return suggestion?.tagKind || suggestion?.kind || 'untyped'
}

export default function TagSuggestions({
  disabled = false,
  loading = false,
  onAccept,
  suggestions = [],
  tags = [],
}) {
  if (suggestions.length === 0) return null

  return (
    <section className="tag-suggestions" aria-labelledby="tag-suggestions-title">
      <h3 id="tag-suggestions-title">Suggested from your Takes</h3>
      <p>
        Model-proposed and reversible. These are not curator tags until you
        accept them.
      </p>
      <div className="tag-suggestions-list">
        {suggestions.map((suggestion, index) => {
          const tag = String(suggestion?.tag || '').trim()
          const polarity = proposalPolarity(suggestion)
          const label = polarity === 'in' ? 'IN' : polarity === 'not_in' ? 'NOT IN' : 'REVIEW'
          const accepted = tags.some((current) => (
            current.tag === tag
            && current.polarity === (polarity === 'in' ? 1 : -1)
          ))
          return (
            <article key={`${tag}-${polarity || 'review'}-${index}`}>
              <div className="tag-suggestion-heading">
                <strong>{tag || 'Untitled proposal'}</strong>
                <span>{label} · {proposalKind(suggestion).replaceAll('_', ' ')}</span>
              </div>
              {proposalQuote(suggestion) && <blockquote>{proposalQuote(suggestion)}</blockquote>}
              {polarity ? (
                <button
                  type="button"
                  aria-label={`Accept ${tag} as ${label}`}
                  disabled={disabled || loading || accepted || !tag}
                  onClick={() => onAccept?.({ tag, polarity })}
                >
                  {accepted ? 'Already tagged' : `Accept as ${label}`}
                </button>
              ) : (
                <span className="tag-suggestion-review">
                  Needs your review; no judgment will be written.
                </span>
              )}
            </article>
          )
        })}
      </div>
    </section>
  )
}
