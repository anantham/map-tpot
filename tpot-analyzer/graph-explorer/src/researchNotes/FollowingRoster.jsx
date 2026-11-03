import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchFollowingRoster } from './researchNotesApi'
import { tagDataAvailable, tagPolarity, tagsFor, matches, validRoster,
  validEvidenceCoverage, sortAccountsByEvidence, coverageStatusLabel } from './followingRosterModel'
import FollowingEvidenceCoverage from './FollowingEvidenceCoverage'
import './FollowingRoster.css'

const PAGE_SIZE = 25

export default function FollowingRoster({ ego, onOpenAccount, tagState = {} }) {
  const [view, setView] = useState({ ego, status: 'idle', roster: null, error: '' })
  const [query, setQuery] = useState('')
  const [tagFilter, setTagFilter] = useState('all')
  const [clueFilter, setClueFilter] = useState('all')
  const [page, setPage] = useState(0)
  const [openError, setOpenError] = useState('')
  const [source, setSource] = useState('latest')
  const [evidenceSort, setEvidenceSort] = useState('')
  const request = useRef(null)
  const requestNumber = useRef(0)
  const currentEgo = useRef(ego)
  currentEgo.current = ego

  useEffect(() => {
    request.current?.abort()
    request.current = null
    requestNumber.current += 1
    setView({ ego, status: 'idle', roster: null, error: '', source: 'latest', coverage: false })
    setQuery('')
    setTagFilter('all')
    setClueFilter('all')
    setPage(0)
    setOpenError('')
    setSource('latest')
    setEvidenceSort('')
    return () => request.current?.abort()
  }, [ego])

  const visibleView = view.ego === ego ? view
    : { ego, status: 'idle', roster: null, error: '', source: 'latest', coverage: false }
  const load = async (selectedSource = source, withCoverage = false) => {
    if (!ego) return
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    const id = ++requestNumber.current
    const requestedEgo = ego
    setSource(selectedSource)
    setView({ ego: requestedEgo, status: 'loading', roster: null, error: '',
      source: selectedSource, coverage: withCoverage })
    setOpenError('')
    try {
      const result = await fetchFollowingRoster({ ego: requestedEgo, signal: controller.signal,
        ...(selectedSource === 'historical' ? { source: selectedSource } : {}),
        ...(withCoverage ? { coverage: true } : {}) })
      if (controller.signal.aborted || id !== requestNumber.current
          || currentEgo.current !== requestedEgo) return
      if (!validRoster(result, requestedEgo)) {
        throw new Error(result?.evidenceCoverage != null && !validEvidenceCoverage(result)
          ? 'Evidence coverage did not match this reviewer. Please retry.'
          : 'The saved list did not match this reviewer. Please try again.')
      }
      setView({ ego: requestedEgo, status: 'loaded', roster: result, error: '',
        source: selectedSource, coverage: withCoverage })
      setPage(0)
    } catch (failure) {
      if (controller.signal.aborted || id !== requestNumber.current
          || currentEgo.current !== requestedEgo) return
      setView({ ego: requestedEgo, status: 'error', roster: null,
        source: selectedSource, coverage: withCoverage,
        error: failure?.message || 'The saved list could not be loaded.' })
    } finally {
      if (request.current === controller) request.current = null
    }
  }

  const roster = visibleView.roster
  const captured = roster?.rosterKind === 'saved_provider_following_capture'
  const cluesAvailable = roster?.recoveredClues?.status === 'available'
  const filtered = useMemo(() => {
    if (!roster || roster.status !== 'available') return []
    const rows = roster.accounts.filter(account => {
      if (clueFilter === 'has_clues' && cluesAvailable && !(account.recoveredClueCount > 0)) return false
      const tags = tagsFor(account, ego, tagState, roster.tagStatus)
      if (!matches(account, tags, query)) return false
      if (tagFilter === 'unknown') return tags === null
      if (tagFilter === 'empty') return tags !== null && tags.length === 0
      if (tagFilter === 'tagged') return tags !== null && tags.length > 0
      return true
    })
    return sortAccountsByEvidence(rows, evidenceSort)
  }, [roster, ego, tagState, query, tagFilter, clueFilter, cluesAvailable, evidenceSort])
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount - 1)
  const pageRows = filtered.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE)
  const tagSummary = useMemo(() => {
    if (!roster || roster.status !== 'available') return { known: 0, tagged: 0, unknown: 0 }
    return roster.accounts.reduce((summary, account) => {
      const tags = tagsFor(account, ego, tagState, roster.tagStatus)
      if (tags === null) summary.unknown += 1
      else {
        summary.known += 1
        if (tags.length) summary.tagged += 1
      }
      return summary
    }, { known: 0, tagged: 0, unknown: 0 })
  }, [roster, ego, tagState])

  return <section className="following-roster" aria-label="Saved following list">
    <h3>Saved following</h3>
    <label className="following-roster-filter">Following list source
      <select value={source} onChange={event => load(event.target.value)} disabled={!ego}>
        <option value="latest">Most recent saved list</option>
        <option value="historical">Historical Archive list</option>
      </select>
    </label>
    <aside className="following-roster-warning" aria-label="Saved list timing">
      {captured ? <>
        <strong>Count-reconciled capture, not a live list.</strong>
        <span>Captured {roster.capturedFrom} to {roster.capturedTo}. Following may have changed since then.</span>
      </> : roster ? <>
        <strong>Historical snapshot, not the current following list.</strong>
        <span>Saved coverage may be incomplete; this is not guaranteed to be a complete list.</span>
      </> : <span>Load the most recent saved list, or choose the historical Archive snapshot. Nothing new is fetched.</span>}
    </aside>
    {visibleView.status === 'error' && <div className="following-roster-error" role="alert">
      <p>Saved following could not be loaded: {visibleView.error}</p>
      <button type="button" onClick={() => load(visibleView.source, visibleView.coverage)}>Retry</button>
    </div>}
    {visibleView.status === 'loading' && <p role="status">Loading saved following…</p>}
    {openError && <p role="alert">{openError}</p>}
    {visibleView.status === 'idle' && <button type="button" onClick={() => load()} disabled={!ego}>
      Browse saved following
    </button>}
    {visibleView.status === 'loaded' && roster?.status === 'not_present' && <p role="status">
      No saved following list is available for this reviewer.
    </p>}
    {visibleView.status === 'loaded' && roster?.status === 'available' && <>
      <div className="following-roster-summary" aria-label="Saved list coverage">
        <span>{roster.total.toLocaleString()} saved accounts</span>
        <span>{roster.counts.withHandle.toLocaleString()} with a handle</span>
        <span>{roster.counts.withoutHandle.toLocaleString()} without a handle</span>
        {cluesAvailable && <span>{roster.recoveredClues.accounts.toLocaleString()} accounts with recovered clues · {roster.recoveredClues.candidates.toLocaleString()} possible values</span>}
        {tagSummary.known > 0 && <span>{tagSummary.tagged.toLocaleString()} tagged of {tagSummary.known.toLocaleString()} accounts with known tags</span>}
        {tagSummary.unknown > 0 && <span>{tagSummary.unknown.toLocaleString()} accounts with tags unknown</span>}
      </div>
      {roster.evidenceCoverage && <div className="following-roster-summary" aria-label="Saved evidence coverage">
        <span>Saved evidence coverage · {roster.evidenceCoverage.status}</span>
        <span>Graph status: {coverageStatusLabel(roster.evidenceCoverage.graph.status)}</span>
        <span>Account nodes: {roster.evidenceCoverage.graph.accountNodes ?? 'unknown'}</span>
        <span>Unresolved nodes: {roster.evidenceCoverage.graph.unresolvedNodes ?? 'unknown'}</span>
        <span>Relationship observations: {roster.evidenceCoverage.graph.relationshipObservations ?? 'unknown'}</span>
        <span>Archive: {coverageStatusLabel(roster.evidenceCoverage.archive.status)} · Website pass: {coverageStatusLabel(roster.evidenceCoverage.websitePass.status)}</span>
        {roster.evidenceCoverage.checkedAt && <span>Checked {roster.evidenceCoverage.checkedAt}</span>}
        <span>{roster.evidenceCoverage.boundary}</span>
      </div>}
      <button type="button" onClick={() => load(source, true)}>
        {roster.evidenceCoverage ? 'Refresh evidence coverage' : 'Load evidence coverage'}
      </button>
      {roster.evidenceCoverage && <p className="following-roster-count">
        Evidence coverage is saved-source observation, not verified ownership or completeness.
      </p>}
      {!tagDataAvailable(roster.tagStatus) && <p className="following-roster-unknown" role="status">
        Tag information is unavailable. “No tags yet” cannot be determined for these accounts.
      </p>}
      {roster.profileLocatorStatus === 'unavailable' && <p role="status">
        Saved profile locators could not be read. Some rows may lack a handle.
      </p>}
      <label className="following-roster-search">
        Search this saved list
        <input value={query} onChange={event => { setQuery(event.target.value); setPage(0) }}
          placeholder="Name, handle, account ID, or tag" />
      </label>
      <label className="following-roster-filter">
        Saved clues filter
        <select value={cluesAvailable ? clueFilter : 'all'} disabled={!cluesAvailable}
          onChange={event => { setClueFilter(event.target.value); setPage(0) }}>
          <option value="all">All accounts</option>
          <option value="has_clues">Has recovered clues</option>
        </select>
      </label>
      {!cluesAvailable && <p role="status">Recovered clue counts are unavailable. This does not mean no other profiles or contact routes exist.</p>}
      {cluesAvailable && <p className="following-roster-count">Counts cover saved candidates only, not verified identities or complete research.</p>}
      <label className="following-roster-filter">
        Tag filter
        <select value={tagFilter} onChange={event => { setTagFilter(event.target.value); setPage(0) }}>
          <option value="all">All accounts</option>
          <option value="empty">No tags yet</option>
          <option value="tagged">Has tags</option>
          <option value="unknown">Tags unknown</option>
        </select>
      </label>
      <p className="following-roster-count" aria-live="polite">
        {filtered.length.toLocaleString()} matching accounts · {pageRows.length} on this page
      </p>
      {roster.evidenceCoverage && <label className="following-roster-filter">
        Sort by evidence
        <select value={evidenceSort} onChange={event => { setEvidenceSort(event.target.value); setPage(0) }}>
          <option value="">Original saved order</option>
          <option value="confirmedPlatforms">Confirmed platforms</option>
          <option value="possiblePlatforms">Possible platforms</option>
          <option value="outgoingFollows">Outgoing follows</option>
          <option value="outgoingReplies">Outgoing reply accounts</option>
          <option value="savedApiPosts">Saved API posts</option>
          <option value="pages">Saved pages</option>
        </select>
      </label>}
      <ul className="following-roster-list">
        {pageRows.map(account => {
          const tags = tagsFor(account, ego, tagState, roster.tagStatus)
          const label = account.username ? `@${account.username}` : `Account ID ${account.accountId}`
          return <li key={account.accountId} className="following-roster-row">
            <div className="following-roster-person">
              <strong>{account.displayName || label}</strong>
              <span>{label} · ID {account.accountId}</span>
              {cluesAvailable && account.recoveredClueCount > 0 && <small>{account.recoveredClueCount} recovered clues</small>}
              {!account.username && <small>No usable saved handle; retained by account ID.</small>}
              {roster.evidenceCoverage && <FollowingEvidenceCoverage account={account} />}
              {tags === null ? <small className="following-roster-tags-unknown">Tags unknown</small>
                : tags.length ? <div className="following-roster-tags" aria-label={`Tags for ${label}`}>
                  {tags.map((item, index) => <span key={`${item.tag}:${item.polarity}:${index}`}>
                    <b>{tagPolarity(item.polarity)}</b> {item.tag}
                  </span>)}
                </div> : <small>No saved tags yet</small>}
              <details className="following-roster-source">
                <summary>Saved row details</summary>
                <span>Source {captured ? 'file: saved following capture' : 'table: archive_following'}</span>
                <span>List owner account ID: {roster.accountId}</span>
                {captured ? <span>Captured row: {account.sourcePointer}</span> : <>
                  <span>Upload date: {account.uploadedAt || 'unknown'}</span>
                  <span>Import date: {account.importedAt || 'unknown'}</span>
                </>}
                <span>Handle source: {account.locatorSource?.kind || 'historical_archive_account'}</span>
                {account.locatorSource?.capturedAt && <span>
                  Profile capture: {account.locatorSource.capturedAt}
                </span>}
                {account.locatorSource?.evidenceRef && <small>
                  Snapshot: {account.locatorSource.evidenceRef.snapshotId}; field:{' '}
                  {account.locatorSource.evidenceRef.sourcePointer}
                </small>}
                <small>{captured ? 'Capture dates are not follow-start dates. Only admitted saved profiles supply handles.'
                  : 'These are upload/import dates, not follow-start dates.'}</small>
              </details>
            </div>
            <button type="button" disabled={!account.username}
              aria-label={`Review ${label}`}
              onClick={() => {
                try {
                  onOpenAccount?.({ accountId: account.accountId,
                    username: account.username, origin: 'following_roster' })
                  setOpenError('')
                } catch (error) {
                  setOpenError(error?.message || 'This saved account could not be opened.')
                }
              }}>
              Review
            </button>
          </li>
        })}
      </ul>
      {!filtered.length && <p>No accounts match these filters.</p>}
      <nav className="following-roster-pages" aria-label="Saved following pages">
        <button type="button" onClick={() => setPage(Math.max(0, currentPage - 1))} disabled={currentPage === 0}>
          Previous
        </button>
        <span>Page {filtered.length ? currentPage + 1 : 0} of {filtered.length ? pageCount : 0}</span>
        <button type="button" onClick={() => setPage(Math.min(pageCount - 1, currentPage + 1))}
          disabled={currentPage >= pageCount - 1}>
          Next
        </button>
      </nav>
    </>}
  </section>
}
