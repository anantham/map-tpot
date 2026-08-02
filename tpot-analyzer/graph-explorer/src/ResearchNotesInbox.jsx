import './ResearchNotesInbox.css'
import './researchNotes/ResearchNotesReview.css'
import { useCallback, useState } from 'react'
import AccountTagPanel from './AccountTagPanel'
import RawDossier from './researchNotes/RawDossier'
import { useResearchNotesInbox } from './researchNotes/useResearchNotesInbox'

function plural(count, singular, pluralForm = `${singular}s`) {
  return count === 1 ? singular : pluralForm
}

function getWorkingIdentity({
  dossier,
  selectedItem,
}) {
  if (!selectedItem) return null
  const accountId = dossier?.account?.accountId
  if (!accountId) return null
  return {
    account: {
      id: String(accountId),
      username: dossier.account.username || selectedItem.handle,
    },
  }
}

export default function ResearchNotesInbox({ ego = '' }) {
  const inbox = useResearchNotesInbox()
  const [curatorEgo, setCuratorEgo] = useState(ego)
  const [tagState, setTagState] = useState({})
  const activeEgo = curatorEgo.trim().replace(/^@/, '').toLowerCase()
  const identity = getWorkingIdentity({
    dossier: inbox.dossier,
    selectedItem: inbox.selectedItem,
  })
  const recordSelectedTagState = useCallback((tags) => {
    if (!activeEgo || !inbox.selectedItem) return
    const stateKey = `${activeEgo}:${inbox.selectedItem.normalizedHandle}`
    setTagState((current) => {
      if (Array.isArray(tags)) return { ...current, [stateKey]: tags }
      if (!Object.prototype.hasOwnProperty.call(current, stateKey)) return current
      const next = { ...current }
      delete next[stateKey]
      return next
    })
  }, [activeEgo, inbox.selectedItem])

  return (
    <main className="research-notes">
      <header className="research-notes-header">
        <div>
          <h1>Research Notes Inbox</h1>
          <p>Inspect evidence, then demonstrate a category by adding or removing tags.</p>
        </div>
        <span className="research-notes-mode">Extensional curation</span>
      </header>

      <div className="research-notes-grid">
        <aside className="research-notes-panel">
          <label htmlFor="research-notes-curator">Curator identity</label>
          <input
            id="research-notes-curator"
            className="research-notes-curator-input"
            value={curatorEgo}
            onChange={(event) => setCuratorEgo(event.target.value)}
            placeholder="e.g. adityaarpitha"
          />
          <p className="research-notes-curator-hint">
            Owns this personal tag extension; graph membership is not required.
          </p>
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
              {inbox.queue.length}{' '}
              {plural(inbox.queue.length, 'account')} in queue
            </span>
            <span>Manual queue · not disagreement-ranked</span>
          </div>
          <nav className="research-notes-queue" aria-label="Research account queue">
            {inbox.queue.map((item) => {
              const stateKey = `${activeEgo}:${item.normalizedHandle}`
              const stateLoaded = Object.prototype.hasOwnProperty.call(
                tagState,
                stateKey,
              )
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
                  className={
                    item.normalizedHandle === inbox.selectedKey ? 'active' : ''
                  }
                  onClick={() => inbox.setSelectedKey(item.normalizedHandle)}
                >
                  <span>@{item.handle}</span>
                  <span className="research-notes-queue-status">{status}</span>
                </button>
              )
            })}
          </nav>
        </aside>

        <div className="research-notes-main">
          {!inbox.selectedItem && (
            <div className="research-notes-state">
              Add at least one account to start the evidence review.
            </div>
          )}
          {inbox.dossierLoading && (
            <div className="research-notes-state">Loading raw dossier…</div>
          )}
          {inbox.dossierError && (
            <div className="research-notes-error">
              <p>{inbox.dossierError}</p>
              {inbox.selectedItem && (
                <a
                  href={`https://x.com/${encodeURIComponent(inbox.selectedItem.normalizedHandle)}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open @{inbox.selectedItem.handle} on X
                </a>
              )}
              <button
                className="research-notes-retry"
                type="button"
                onClick={inbox.retryDossier}
              >
                Retry dossier
              </button>
            </div>
          )}
          {inbox.dossier && <RawDossier dossier={inbox.dossier} />}

          {inbox.selectedItem && (
            <section className="research-notes-judgment">
              <h2>Working extension</h2>
              <p className="research-notes-question">
                The category is demonstrated by the accounts you include and
                exclude. No first-principles definition is required here.
              </p>
              <div className="research-notes-provenance" role="note">
                Ego-scoped mutable curator tags · add/remove activity and its
                source retained separately from the current tag state
              </div>
              {identity ? (
                <AccountTagPanel
                  key={`${activeEgo}:${identity.account.id}`}
                  ego={activeEgo}
                  account={identity.account}
                  onTagStateLoaded={recordSelectedTagState}
                />
              ) : (
                <p className="research-notes-empty">
                  {inbox.dossierError
                    ? 'Tagging stays locked until retry resolves a stable archive account ID.'
                    : 'Resolving a stable archive account ID before loading tags…'}
                </p>
              )}
              <label htmlFor="research-notes-investigation-note">
                Investigation note
              </label>
              <textarea
                id="research-notes-investigation-note"
                className="research-notes-note"
                value={inbox.note}
                onChange={(event) => inbox.setNote(event.target.value)}
              />
              <p className="research-notes-preview-warning">
                This investigation note is session-only. Account tags are the
                durable working extension; they are mutable and are not a frozen
                evaluation set.
              </p>
              <div className="research-notes-model-state">
                <h2>Model position</h2>
                <p>
                  Unavailable: no target-scoped prediction has been run for
                  this working tag extension.
                </p>
                <p>
                  Legacy NMF percentages are intentionally not shown as soft
                  membership. Until a compatible prediction exists, this queue
                  remains manual rather than disagreement-ranked.
                </p>
              </div>
            </section>
          )}
        </div>
      </div>
    </main>
  )
}
