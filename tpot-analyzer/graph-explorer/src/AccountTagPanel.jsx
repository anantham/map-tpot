import { useMemo, useState } from 'react'

import './researchNotes/AccountTagPanel.css'
import TagAssignments from './researchNotes/TagAssignments'
import TagAutocomplete from './researchNotes/TagAutocomplete'
import TagHistory from './researchNotes/TagHistory'
import TagMetaNote from './researchNotes/TagMetaNote'
import TagSuggestions from './researchNotes/TagSuggestions'
import { useAccountTagWorkspace } from './researchNotes/useAccountTagWorkspace'

const normalized = (value) => String(value || '').trim().toLowerCase()

export default function AccountTagPanel({
  account,
  activeTag = '',
  ego,
  onActiveTagChange,
  onHistoryLoaded,
  onTagChanged,
  onTagStateLoaded,
  onVocabularyLoaded,
  renderHistory = true,
  suggestions = [],
  vocabulary = [],
}) {
  const [tagDraft, setTagDraft] = useState('')
  const workspace = useAccountTagWorkspace({
    accountId: account?.id,
    ego,
    onHistoryLoaded,
    onTagChanged,
    onTagStateLoaded,
    onVocabularyLoaded,
  })
  const normalizedDraft = tagDraft.trim()
  const searchableTags = useMemo(() => [...new Set([
    ...workspace.availableTags,
    ...vocabulary,
    ...suggestions.map((suggestion) => suggestion?.tag),
  ].map((tag) => String(tag || '').trim()).filter(Boolean))], [
    suggestions,
    vocabulary,
    workspace.availableTags,
  ])
  const existing = workspace.tags.find((tag) => (
    normalized(tag.tag) === normalized(normalizedDraft)
  ))

  const mark = async (polarity) => {
    const saved = await workspace.saveTag({ tag: normalizedDraft, polarity })
    if (saved) {
      onActiveTagChange?.(normalizedDraft)
      setTagDraft('')
    }
  }

  const acceptSuggestion = async ({ tag, polarity }) => {
    const saved = await workspace.saveTag({ tag, polarity })
    if (saved) onActiveTagChange?.(tag)
    return saved
  }

  const selectTag = (tag) => {
    setTagDraft(tag)
    onActiveTagChange?.(tag)
  }

  const buttonLabel = (polarity, label) => {
    if (!existing) return `Mark ${label}`
    if (existing.polarity === polarity) return `Already ${label}`
    return `Change to ${label}`
  }

  return (
    <section className="account-tag-panel" aria-labelledby="account-tag-panel-title">
      <header className="account-tag-panel-header">
        <div>
          <h2 id="account-tag-panel-title">
            Current tags for @{account?.username || account?.id}
          </h2>
          <p>This is your current, reversible judgment for this account.</p>
        </div>
      </header>
      {!workspace.canEdit && <p>Set a curator identity to tag accounts.</p>}
      {workspace.error && (
        <div className="account-tag-error" role="alert">
          <span>{workspace.error}</span>
          {!workspace.tagsLoaded && workspace.canEdit && (
            <button type="button" onClick={workspace.load}>Retry tags</button>
          )}
        </div>
      )}
      {workspace.vocabularyError && (
        <div className="account-tag-error" role="alert">{workspace.vocabularyError}</div>
      )}

      <TagSuggestions
        disabled={!workspace.canMutate}
        dismissalScope={`${ego || 'anonymous'}:${account?.id || 'unknown'}`}
        loading={workspace.loading}
        onAccept={acceptSuggestion}
        suggestions={suggestions}
        tags={workspace.tags}
      />

      <div className="tag-marking-control">
        <TagAutocomplete
          disabled={!workspace.canMutate || workspace.loading}
          onChange={setTagDraft}
          onSelect={selectTag}
          tags={searchableTags}
          value={tagDraft}
        />
        <div className="tag-polarity-actions" aria-label="Choose tag judgment">
          <button
            type="button"
            className="mark-in"
            disabled={!workspace.canMutate || workspace.loading || !normalizedDraft || existing?.polarity === 1}
            onClick={() => mark('in')}
          >
            {buttonLabel(1, 'IN')}
          </button>
          <button
            type="button"
            className="mark-not-in"
            disabled={!workspace.canMutate || workspace.loading || !normalizedDraft || existing?.polarity === -1}
            onClick={() => mark('not_in')}
          >
            {buttonLabel(-1, 'NOT IN')}
          </button>
        </div>
      </div>

      <div className="account-tag-status" aria-live="polite">
        {workspace.loading && !workspace.tagsLoaded ? 'Loading tags…' : ''}
      </div>
      {workspace.tagsLoaded && (
        <TagAssignments
          disabled={!workspace.canMutate || workspace.loading}
          onRemove={workspace.removeTag}
          onSelect={selectTag}
          tags={workspace.tags}
        />
      )}
      <TagMetaNote
        key={`${ego || ''}:${activeTag || ''}`}
        disabled={!workspace.canMutate}
        ego={ego}
        tag={activeTag}
      />
      {renderHistory && <TagHistory events={workspace.events} />}
    </section>
  )
}
