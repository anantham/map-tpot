const QUESTIONS = [
  { key: 'relevance', label: 'Relevant to your Dharma search?',
    choices: [['IN', 'Yes'], ['OUT', 'No'], ['ABSTAIN', 'Not sure']] },
  { key: 'known', label: 'Did you already know this account?',
    choices: [['YES', 'Yes'], ['NO', 'No'], ['UNSURE', 'Not sure']] },
  { key: 'glad', label: 'Glad it surfaced?',
    choices: [['YES', 'Yes'], ['NO', 'No'], ['UNSURE', 'Not sure']] },
]

export default function DiscoveryReviewQuestions({ draft, update, disabled, relevanceQuestion, accountLabel }) {
  return (
    <div className="discovery-review-questions">
      <p className="discovery-review-eyebrow">Your take{accountLabel ? ` on ${accountLabel}` : ''}</p>
      {QUESTIONS.map(({ key, label, choices }) => (
        <fieldset key={key} disabled={disabled}>
          <legend>{key === 'relevance' ? relevanceQuestion || label : label}</legend>
          <div className="discovery-review-choices">
            {choices.map(([value, text]) => (
              <label className={draft[key] === value ? 'is-selected' : ''} key={value}>
                <input type="radio" name={`discovery-${key}`} value={value}
                  checked={draft[key] === value} onChange={() => update(key, value)} />
                <span>{text}</span>
              </label>
            ))}
          </div>
        </fieldset>
      ))}
      <label className="discovery-review-note" htmlFor="discovery-review-note">
        Anything to add? <span>Optional</span>
      </label>
      <textarea id="discovery-review-note" value={draft.note} disabled={disabled}
        maxLength={4000} rows={3} placeholder="What caught your attention?"
        onChange={(event) => update('note', event.target.value)} />
    </div>
  )
}
