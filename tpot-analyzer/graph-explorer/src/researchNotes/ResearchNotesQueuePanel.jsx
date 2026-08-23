const plural = (count, singular, pluralForm = `${singular}s`) => (
  count === 1 ? singular : pluralForm
)

const shortReceipt = (value) => String(value || '').slice(0, 12)

export default function ResearchNotesQueuePanel({
  activeEgo,
  curatorEgo,
  inbox,
  onCuratorChange,
  tagState,
}) {
  return (
    <aside className="research-notes-panel">
      <label htmlFor="research-notes-curator">Curator identity</label>
      <input
        id="research-notes-curator"
        className="research-notes-curator-input"
        value={curatorEgo}
        onChange={(event) => onCuratorChange(event.target.value)}
        placeholder="e.g. adityaarpitha"
      />
      <p className="research-notes-curator-hint">
        Owns the personal tag extension below; graph membership is not
        required. The research queue and account notes are device-wide on this
        browser, not curator-scoped.
      </p>
      {inbox.sourceLoading && (
        <p className="research-notes-source-state">Loading configured research source…</p>
      )}
      {inbox.source && (
        <p className="research-notes-source-state">
          {inbox.sourceError ? 'Last loaded' : 'Loaded'} from {inbox.source.name}
          {' '}· proposals remain unconfirmed
        </p>
      )}
      {inbox.sourceError && (
        <p className="research-notes-source-error">
          Takes source unavailable: {inbox.sourceError}. Manual paste still works.
        </p>
      )}
      {inbox.proposalMetadata && (
        <div className="research-notes-proposal-warning" role="alert">
          <p>
            {inbox.proposalMetadata.status === 'stale'
              ? 'Suggestions are stale and hidden. Your current Takes accounts are still loaded.'
              : 'Suggestions are invalid and hidden. Your current Takes accounts are still loaded.'}
          </p>
          {inbox.proposalMetadata.status === 'stale' && (
            <p>
              Proposal receipt: <code>
                {shortReceipt(inbox.proposalMetadata.boundSourceSha256)} →{' '}
                {shortReceipt(inbox.proposalMetadata.currentSourceSha256)}
              </code>
            </p>
          )}
          <p>
            Automated regeneration is not available here yet. Regenerate the
            proposal file, then reload this source.
          </p>
          <button type="button" onClick={inbox.reloadSource}>
            Reload Takes source
          </button>
        </div>
      )}
      {inbox.persistenceWarning && (
        <p className="research-notes-persistence-warning" role="alert">
          {inbox.persistenceWarning}
        </p>
      )}
      <label htmlFor="research-notes-paste">Paste accounts and notes</label>
      <textarea
        id="research-notes-paste"
        className="research-notes-input"
        value={inbox.pasteText}
        onChange={(event) => inbox.setPasteText(event.target.value)}
        placeholder="@handle, X profile URL, and whatever you currently believe"
      />
      <button
        className="research-notes-primary"
        type="button"
        onClick={inbox.addToQueue}
      >
        Add to queue
      </button>
      <div className="research-notes-progress">
        <span>
          {inbox.queue.length} {plural(inbox.queue.length, 'account')} in queue
        </span>
        <span>
          {inbox.source && inbox.manualQueueCount > 0
            ? 'Takes + browser-local queue'
            : inbox.source
              ? 'Takes-backed queue · proposals only'
              : inbox.persistenceEnabled
                ? 'Browser-local queue · not disagreement-ranked'
                : 'In-memory queue · browser storage unavailable'}
        </span>
      </div>
      <nav className="research-notes-queue" aria-label="Research account queue">
        {inbox.queue.map((item) => {
          const stateKey = `${activeEgo}:${item.normalizedHandle}`
          const stateLoaded = Object.prototype.hasOwnProperty.call(tagState, stateKey)
          const assignments = tagState[stateKey]
          const status = stateLoaded
            ? (assignments.length
                ? `${assignments.length} ${plural(assignments.length, 'tag')}`
                : 'unclassified')
            : 'tags not loaded'
          return (
            <button
              type="button"
              key={item.normalizedHandle}
              aria-label={`@${item.handle} ${status}`}
              className={item.normalizedHandle === inbox.selectedKey ? 'active' : ''}
              onClick={() => inbox.setSelectedKey(item.normalizedHandle)}
            >
              <span>@{item.handle}</span>
              <span className="research-notes-queue-status">{status}</span>
            </button>
          )
        })}
      </nav>
    </aside>
  )
}
