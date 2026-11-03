import { useEffect } from 'react'
import DiscoveryReviewCard from './DiscoveryReviewCard'
import DiscoveryReviewQuestions from './DiscoveryReviewQuestions'
import useDiscoveryReview, { isComplete } from './useDiscoveryReview'
import './DiscoveryReview.css'

export default function DiscoveryReview({ apiMode = 'relative' }) {
  const review = useDiscoveryReview(apiMode)
  const { packet, card, index, draft, saving, completedCount, unsavedCount } = review
  const total = packet?.cards.length || 0
  const title = packet ? packet.purpose?.title || 'Dharma discovery' : 'Account discovery'
  const usefulNew = Object.values(review.answers).filter((answer) =>
    answer.relevance === 'IN' && answer.known === 'NO' && answer.glad === 'YES').length
  useEffect(() => { document.title = `${title} · Private review` }, [title])
  const status = saving ? 'Saving…' : review.dirty ? 'Unsaved changes' : review.answer
    ? 'Saved' : 'Not saved yet'

  return (
    <main className="discovery-review">
      <div className="discovery-review-shell">
        <header className="discovery-review-heading">
          <div>
            <p className="discovery-review-eyebrow">A few accounts to explore</p>
            <h1>{title}</h1>
            <p>{packet?.purpose?.description || 'Take a look. Tell us what feels relevant and worth finding.'}</p>
          </div>
          {packet && <span className="discovery-review-private">Private review</span>}
        </header>

        {review.loading && <p className="discovery-review-state" role="status">Loading your review…</p>}
        {review.loadError && (
          <div className="discovery-review-error" role="alert">
            <p>{review.loadError}</p>
            <button type="button" onClick={review.retry}>Try again</button>
          </div>
        )}
        {!review.loading && !review.loadError && packet && (
          <>
            <div className="discovery-review-progress">
              <div>
                <strong>{completedCount} of {total} reviewed</strong>
                <progress max={total || 1} value={completedCount} aria-label="Review progress" />
              </div>
              {!!total && <label>
                <span>Go to account</span>
                <select value={index} disabled={saving}
                  onChange={(event) => review.navigate(Number(event.target.value))}>
                  {packet.cards.map((item, position) => (
                    <option value={position} key={item.accountId}>
                      {position + 1}. {item.username ? `@${item.username}` : `Account ${item.accountId}`}
                      {isComplete(review.answers[item.accountId]) ? ' · reviewed' : ''}
                    </option>
                  ))}
                </select>
              </label>}
            </div>
            <p className="discovery-review-feedback" role="status">
              <strong>{usefulNew} useful new {usefulNew === 1 ? 'find' : 'finds'} confirmed</strong>
              <span>Saved “Yes, relevant” + “No, didn’t know” + “Yes, glad.”
                {' '}Ranking has not changed; these answers will inform the comparison.</span>
            </p>
            {unsavedCount > 0 && (
              <p className="discovery-review-draft-status" role="status">
                {unsavedCount} {unsavedCount === 1 ? 'account has' : 'accounts have'} unsaved choices.
                {' '}They stay here while you browse. Save before leaving or reloading.
              </p>
            )}
            {total > 0 && completedCount === total && (
              <div className="discovery-review-complete" role="status">
                <strong>All {total} reviewed. Thank you.</strong>
                <span>Your answers are saved. You can revisit any account below.</span>
              </div>
            )}
            {!card && <p className="discovery-review-state">There are no accounts in this review.</p>}
            {card && (
              <>
                <div className="discovery-review-position">
                  <span>Account {index + 1} of {total}</span>
                  <a className="discovery-review-answer-jump" href="#review-answers">Your take ↓</a>
                  <span className={review.dirty ? 'is-unsaved' : ''} role="status">{status}</span>
                </div>
                <div className="discovery-review-layout">
                  <DiscoveryReviewCard card={card} />
                  <section id="review-answers" className="discovery-review-answer" aria-label="Your review answers">
                    <DiscoveryReviewQuestions draft={draft} update={review.update} disabled={saving}
                      relevanceQuestion={packet.purpose?.relevanceQuestion}
                      accountLabel={card.username ? `@${card.username}` : `account ${card.accountId}`} />
                    {review.saveError && <p className="discovery-review-error" role="alert">{review.saveError}</p>}
                    {!isComplete(draft) && <p className="discovery-review-help">Choose one answer in each row to save.</p>}
                    <div className="discovery-review-save-actions">
                      <button type="button" disabled={saving || !isComplete(draft) || !review.dirty}
                        onClick={() => review.save(false)}>Save answers</button>
                      <button className="discovery-review-primary" type="button"
                        disabled={saving || !isComplete(draft)} onClick={() => review.save(true)}>
                        {saving ? 'Saving…' : review.answer && !review.dirty
                          ? index === total - 1 ? 'Saved' : 'Next account'
                          : index === total - 1 ? 'Save & finish' : 'Save & next'}
                      </button>
                    </div>
                  </section>
                </div>
                <nav className="discovery-review-navigation" aria-label="Browse review accounts">
                  <button type="button" disabled={saving || index === 0}
                    onClick={() => review.navigate(index - 1)}>← Back</button>
                  <span>{index + 1} / {total}</span>
                  <button type="button" disabled={saving || index === total - 1}
                    onClick={() => review.navigate(index + 1)}>Next →</button>
                </nav>
              </>
            )}
          </>
        )}
      </div>
    </main>
  )
}
