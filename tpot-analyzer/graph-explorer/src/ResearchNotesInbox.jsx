import './ResearchNotesInbox.css'
import RawDossier from './researchNotes/RawDossier'
import { useResearchNotesInbox } from './researchNotes/useResearchNotesInbox'

const JUDGMENTS = [
  { value: 'in', label: 'IN' },
  { value: 'out', label: 'OUT' },
  { value: 'abstain', label: 'ABSTAIN' },
]

function plural(count, singular, pluralForm = `${singular}s`) {
  return count === 1 ? singular : pluralForm
}

export default function ResearchNotesInbox() {
  const inbox = useResearchNotesInbox()

  return (
    <main className="research-notes">
      <header className="research-notes-header">
        <div>
          <h1>Research Notes Inbox</h1>
          <p>Paste messy leads, inspect raw evidence, then make an explicit judgment.</p>
        </div>
        <span className="research-notes-mode">Unbound preview</span>
      </header>

      <div className="research-notes-grid">
        <aside className="research-notes-panel">
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
            <span>Session-only preview</span>
          </div>
          <nav className="research-notes-queue" aria-label="Research account queue">
            {inbox.queue.map((item) => (
              <button
                type="button"
                key={item.normalizedHandle}
                className={
                  item.normalizedHandle === inbox.selectedKey ? 'active' : ''
                }
                onClick={() => inbox.setSelectedKey(item.normalizedHandle)}
              >
                <span>@{item.handle}</span>
                <span className="research-notes-queue-status">review</span>
              </button>
            ))}
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
              <h2>Draft judgment</h2>
              <p className="research-notes-question">
                A canonical target and question must come from a frozen task,
                not editable client configuration.
              </p>
              <div className="research-notes-judgment-options">
                {JUDGMENTS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    className={inbox.judgment === option.value ? 'active' : ''}
                    aria-pressed={inbox.judgment === option.value}
                    onClick={() => inbox.setJudgment(option.value)}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
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
                This draft is session-only. Saving stays locked until the server
                supplies both a canonical task and snapshot-addressed evidence.
              </p>
              <div className="research-notes-actions">
                <button
                  className="research-notes-primary"
                  type="button"
                  disabled
                >
                  Save judgment
                </button>
              </div>
            </section>
          )}
        </div>
      </div>
    </main>
  )
}
