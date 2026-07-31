import './ResearchNotesInbox.css'
import './researchNotes/ResearchNotesReview.css'
import RawDossier from './researchNotes/RawDossier'
import { useResearchNotesInbox } from './researchNotes/useResearchNotesInbox'

const JUDGMENTS = [
  { value: 'in', label: 'IN' },
  { value: 'out', label: 'OUT' },
  { value: 'abstain', label: 'ABSTAIN' },
]

const PROVISIONAL_PROBES = [
  {
    id: 'dharma-retrieval-relevance',
    label: 'Probe A — Retrieval relevance',
    question: 'Should this person be surfaced when searching for people relevant to Dharma, meditation, or jhāna community-building?',
    hint: 'This tests a search policy. It does not claim that the person belongs to a social group.',
  },
  {
    id: 'dharma-social-affiliation',
    label: 'Probe B — Social affiliation',
    question: 'Based on public evidence, is this person socially affiliated with the Dharma community as you use that term?',
    hint: 'This tests a group boundary. It does not claim competence, intent, endorsement, or spiritual attainment.',
  },
]

function plural(count, singular, pluralForm = `${singular}s`) {
  return count === 1 ? singular : pluralForm
}

function draftedProbeCount(draft) {
  return Object.values(draft?.judgments || {}).filter(Boolean).length
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
            <span>
              {Object.values(inbox.drafts).reduce(
                (total, draft) => total + draftedProbeCount(draft),
                0,
              )}
              /{inbox.queue.length * PROVISIONAL_PROBES.length} provisional answers
            </span>
          </div>
          <nav className="research-notes-queue" aria-label="Research account queue">
            {inbox.queue.map((item) => {
              const drafted = draftedProbeCount(inbox.drafts[item.normalizedHandle])
              const status = drafted
                ? `${drafted}/${PROVISIONAL_PROBES.length} drafted`
                : 'review'
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
              <h2>Provisional boundary probes</h2>
              <p className="research-notes-question">
                These answers are allowed to disagree. That disagreement helps
                test whether useful retrieval and social affiliation are
                genuinely different targets.
              </p>
              {PROVISIONAL_PROBES.map((probe) => (
                <fieldset className="research-notes-probe" key={probe.id}>
                  <legend>{probe.label}</legend>
                  <p className="research-notes-question">{probe.question}</p>
                  <p className="research-notes-probe-hint">{probe.hint}</p>
                  <div className="research-notes-judgment-options">
                    {JUDGMENTS.map((option) => {
                      const active = inbox.probeJudgments[probe.id] === option.value
                      return (
                        <button
                          key={option.value}
                          type="button"
                          className={active ? 'active' : ''}
                          aria-pressed={active}
                          onClick={() => inbox.setProbeJudgment(probe.id, option.value)}
                        >
                          {option.label}
                        </button>
                      )
                    })}
                  </div>
                </fieldset>
              ))}
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
                These formative drafts are session-only and are not gold labels.
                Saving stays locked until the server supplies a canonical task,
                snapshot-addressed evidence, and safe retry semantics.
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
