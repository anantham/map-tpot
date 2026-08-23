import { xProfileUrl } from './researchNotes/xProfileUrl'
import './ResearchNotesInbox.css'
import './researchNotes/ResearchNotesReview.css'
import { useCallback, useState } from 'react'
import AccountTagPanel from './AccountTagPanel'
import RawDossier from './researchNotes/RawDossier'
import ResearchNotesQueuePanel from './researchNotes/ResearchNotesQueuePanel'
import TagHistory from './researchNotes/TagHistory'
import WorkingTagImpact from './researchNotes/WorkingTagImpact'
import { useResearchNotesInbox } from './researchNotes/useResearchNotesInbox'
import { useWorkingTagSelection } from './researchNotes/useWorkingTagSelection'

function getWorkingIdentity({
  dossier,
  selectedItem,
}) {
  if (!selectedItem) return null
  const accountId = dossier?.account?.accountId || selectedItem.accountId
  if (!accountId) return null
  return {
    account: {
      id: String(accountId),
      username: dossier?.account?.username || selectedItem.handle,
    },
  }
}

export default function ResearchNotesInbox({ ego = '' }) {
  const [curatorEgo, setCuratorEgo] = useState(ego)
  const [historyState, setHistoryState] = useState({})
  const [tagState, setTagState] = useState({})
  const activeEgo = curatorEgo.trim().replace(/^@/, '').toLowerCase()
  const inbox = useResearchNotesInbox()
  const identity = getWorkingIdentity({
    dossier: inbox.dossier,
    selectedItem: inbox.selectedItem,
  })
  const selectedHandle = inbox.selectedItem?.normalizedHandle || ''
  const workingTag = useWorkingTagSelection({
    selectedHandle,
    suggestionsByHandle: inbox.suggestionsByHandle,
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
  const recordSelectedHistory = useCallback((events) => {
    if (!activeEgo || !inbox.selectedItem) return
    const stateKey = `${activeEgo}:${inbox.selectedItem.normalizedHandle}`
    setHistoryState((current) => ({ ...current, [stateKey]: events }))
  }, [activeEgo, inbox.selectedItem])
  const selectedStateKey = inbox.selectedItem
    ? `${activeEgo}:${inbox.selectedItem.normalizedHandle}`
    : ''
  const selectedHistoryKnown = Object.prototype.hasOwnProperty.call(
    historyState,
    selectedStateKey,
  )
  const selectedHistory = historyState[selectedStateKey]
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
        <ResearchNotesQueuePanel
          activeEgo={activeEgo}
          curatorEgo={curatorEgo}
          inbox={inbox}
          onCuratorChange={setCuratorEgo}
          tagState={tagState}
        />

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
                  href={xProfileUrl(inbox.selectedItem.normalizedHandle)}
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
              <h2>Your tags for @{inbox.selectedItem.handle}</h2>
              <p className="research-notes-question">
                Mark this account IN or NOT IN for any tags that matter to you.
                You can change or retract every judgment later.
              </p>
              <div className="research-notes-provenance" role="note">
                Your mutable working set · model suggestions do nothing until
                you accept them
              </div>
              <label htmlFor="research-notes-investigation-note">
                Notes about this account
              </label>
              <textarea
                id="research-notes-investigation-note"
                className="research-notes-note"
                value={inbox.note}
                onChange={(event) => inbox.setNote(event.target.value)}
              />
              <p className="research-notes-preview-warning">
                {inbox.persistenceEnabled
                  ? 'Saved in this browser’s device-wide research queue. '
                  : 'Currently held in memory only. '}
                A tag’s working meaning is versioned separately below.
              </p>
              {identity ? (
                <AccountTagPanel
                  key={`${activeEgo}:${identity.account.id}`}
                  activeTag={workingTag.activeTag}
                  ego={activeEgo}
                  account={identity.account}
                  onActiveTagChange={workingTag.selectTag}
                  onHistoryLoaded={recordSelectedHistory}
                  suggestions={workingTag.selectedSuggestions}
                  onTagChanged={workingTag.tagChanged}
                  onTagStateLoaded={recordSelectedTagState}
                  onVocabularyLoaded={workingTag.recordVocabulary}
                  renderHistory={false}
                  vocabulary={workingTag.availableTags}
                />
              ) : (
                <p className="research-notes-empty">
                  {inbox.dossierError
                    ? 'Tagging stays locked until retry resolves a stable archive account ID.'
                    : 'Resolving a stable archive account ID before loading tags…'}
                </p>
              )}
            </section>
          )}

          {inbox.selectedItem && (
            <aside className="research-notes-consequence">
              {workingTag.activeTag && activeEgo ? (
                <WorkingTagImpact
                  availableTags={workingTag.availableTags}
                  ego={activeEgo}
                  onReviewCandidate={inbox.addCandidate}
                  onTagChange={workingTag.selectTag}
                  revision={workingTag.revision}
                  tag={workingTag.activeTag}
                  tagKind={workingTag.activeTagKind}
                />
              ) : (
                <div className="research-notes-model-state">
                  <h2>What this tag currently surfaces</h2>
                  <h3>Model opinion — none yet (needs more tags)</h3>
                  <p>
                    Choose or add a tag to calculate its first selective-follow
                    candidate list.
                  </p>
                  <p>
                    Legacy NMF percentages are intentionally not shown as soft
                    membership.
                  </p>
                </div>
              )}
            </aside>
          )}

          {inbox.selectedItem && selectedHistoryKnown && (
            <section className="research-notes-audit" aria-label="Audit history">
              {Array.isArray(selectedHistory) ? (
                <TagHistory events={selectedHistory} />
              ) : (
                <p>Recent changes are unavailable until tag state reloads.</p>
              )}
            </section>
          )}
        </div>
      </div>
    </main>
  )
}
