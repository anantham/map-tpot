import AccountTagPanel from '../AccountTagPanel'
import TagHistory from './TagHistory'
import WorkingTagImpact from './WorkingTagImpact'

export default function AccountJudgmentDrawer({
  activeEgo,
  identity,
  identityBlocked,
  note,
  onHistoryLoaded,
  onNoteChange,
  onReviewCandidate,
  onTagStateLoaded,
  persistenceEnabled,
  selectedHandle,
  selectedHistory,
  selectedHistoryKnown,
  workingTag,
}) {
  if (!selectedHandle) return null

  return (
    <section
      className="account-judgment-drawer"
      aria-label={`Review @${selectedHandle}`}
    >
      <header className="account-judgment-header">
        <div>
          <span className="account-judgment-kicker">Current account</span>
          <h2>Review @{selectedHandle}</h2>
        </div>
        <p>Update any tags that fit. Every change remains reversible.</p>
      </header>

      <details className="account-note-disclosure">
        <summary>
          <span>Account note</span>
          <span>{persistenceEnabled ? 'Saved locally' : 'Held in memory'}</span>
        </summary>
        <label htmlFor="research-notes-investigation-note">
          What changed or supported your view?
        </label>
        <textarea
          aria-label="Notes about this account"
          id="research-notes-investigation-note"
          className="research-notes-note"
          value={note}
          onChange={(event) => onNoteChange(event.target.value)}
        />
        <p>
          This account-level note is separate from the versioned meaning of a tag.
        </p>
      </details>

      {!activeEgo && (
        <p className="research-notes-reviewer-gate">
          Set reviewer identity in the queue to edit this account.
        </p>
      )}

      {activeEgo && identity && (
        <AccountTagPanel
          key={`${activeEgo}:${identity.account.id}`}
          activeTag={workingTag.activeTag}
          ego={activeEgo}
          account={identity.account}
          onActiveTagChange={workingTag.selectTag}
          onHistoryLoaded={onHistoryLoaded}
          suggestions={workingTag.selectedSuggestions}
          onTagChanged={workingTag.tagChanged}
          onTagStateLoaded={onTagStateLoaded}
          onVocabularyLoaded={workingTag.recordVocabulary}
          renderHistory={false}
          vocabulary={workingTag.availableTags}
        />
      )}

      {activeEgo && !identity && (
        <p className="research-notes-empty">
          {identityBlocked
            ? 'Tagging stays locked until retry resolves a stable archive account ID.'
            : 'Resolving a stable archive account ID before loading tags…'}
        </p>
      )}

      {workingTag.activeTag && activeEgo && (
        <details className="research-notes-consequence">
          <summary>See what “{workingTag.activeTag}” currently surfaces</summary>
          <WorkingTagImpact
            availableTags={workingTag.availableTags}
            ego={activeEgo}
            onReviewCandidate={onReviewCandidate}
            onTagChange={workingTag.selectTag}
            revision={workingTag.revision}
            tag={workingTag.activeTag}
            tagKind={workingTag.activeTagKind}
          />
        </details>
      )}

      {selectedHistoryKnown && (
        <section className="research-notes-audit" aria-label="Audit history">
          {Array.isArray(selectedHistory) ? (
            <TagHistory events={selectedHistory} />
          ) : (
            <p>Recent changes are unavailable until tag state reloads.</p>
          )}
        </section>
      )}

      <details className="account-judgment-provenance">
        <summary>How this workspace treats evidence</summary>
        <p>
          Model suggestions do nothing until you accept them. Your mutable
          working judgments stay distinct from frozen study snapshots.
        </p>
      </details>
    </section>
  )
}
