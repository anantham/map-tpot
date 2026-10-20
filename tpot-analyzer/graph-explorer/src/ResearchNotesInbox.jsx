import { xProfileUrl } from './researchNotes/xProfileUrl'
import './ResearchNotesInbox.css'
import './researchNotes/ResearchNotesReview.css'
import { useCallback, useState } from 'react'
import AccountJudgmentDrawer from './researchNotes/AccountJudgmentDrawer'
import RawDossier from './researchNotes/RawDossier'
import ResearchNotesQueuePanel from './researchNotes/ResearchNotesQueuePanel'
import { useResearchNotesInbox } from './researchNotes/useResearchNotesInbox'
import { useWorkingTagSelection } from './researchNotes/useWorkingTagSelection'
import DiscoveryReview from './DiscoveryReview'

function getWorkingIdentity({
  dossier,
  selectedItem,
}) {
  if (!selectedItem) return null
  const accountId = dossier?.account?.accountId || selectedItem.accountId
  if (!accountId) return null
  if (String(accountId).startsWith('shadow:')) return null
  return {
    account: {
      id: String(accountId),
      username: dossier?.account?.username || selectedItem.handle,
    },
  }
}

export default function ResearchNotesInbox({ ego = '' }) {
  if (new URLSearchParams(window.location.search).get('review') === 'discovery') {
    return <DiscoveryReview apiMode="local" />
  }
  return <AccountResearchNotesInbox ego={ego} />
}

function AccountResearchNotesInbox({ ego }) {
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
          <h1>Review</h1>
          <p>Investigate one account, record what changed your mind, then continue.</p>
        </div>
        <a className="research-notes-mode" href="?view=research-notes&review=discovery">
          Discovery review
        </a>
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

          <AccountJudgmentDrawer
            activeEgo={activeEgo}
            identity={identity}
            identityBlocked={Boolean(inbox.dossierError)}
            note={inbox.note}
            onHistoryLoaded={recordSelectedHistory}
            onNoteChange={inbox.setNote}
            onReviewCandidate={inbox.addCandidate}
            onTagStateLoaded={recordSelectedTagState}
            persistenceEnabled={inbox.persistenceEnabled}
            selectedHandle={inbox.selectedItem?.handle || ''}
            selectedHistory={selectedHistory}
            selectedHistoryKnown={selectedHistoryKnown}
            workingTag={workingTag}
          />
        </div>
      </div>
    </main>
  )
}
