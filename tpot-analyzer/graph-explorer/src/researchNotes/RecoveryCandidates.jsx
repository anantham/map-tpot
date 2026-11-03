import FollowPath from './FollowPath'
import InteractionPath from './InteractionPath'

const label = row => row.username ? `@${row.username}` : `Account ID ${row.accountId}`

export default function RecoveryCandidates({ result, method, onReviewCandidate }) {
  return result.candidates.map((candidate, index) => <article key={candidate.accountId}>
    <strong>#{index + 1} {label(candidate)}</strong>
    <p>Why this person: {method === 'popularity'
      ? `${candidate.globalSupport} distinct accounts link to them in this observed graph. This baseline ignores your seeds.`
      : `${candidate.supportingSeeds} of your IN examples reach this account within ${method === 'two_hop' ? 'two hops' : 'one hop'}.`}</p>
    <p>{method === 'shared' ? 'Score counts distinct seeds, not repeated activity.' :
      method === 'selectivity' ? 'Each seed contributes 1 / its observed walk degree. Incomplete capture can overstate selectivity.' :
      method === 'two_hop' ? 'Half one-step, half two-step mass; each step is divided by the observed number of neighbors.' : ''}</p>
    <button type="button" disabled={!candidate.username} onClick={() => onReviewCandidate?.(candidate)}>
      {candidate.username ? `Review ${label(candidate)}` : 'Handle unavailable'}
    </button>
    {candidate.paths.map((path, pathIndex) => path.kind === 'follows'
      ? <FollowPath key={pathIndex} path={path} />
      : <InteractionPath key={pathIndex} path={path} onOpenAccount={onReviewCandidate} />)}
    <small>{candidate.shownPaths} representative path(s) shown, not all contributing paths.</small>
  </article>)
}
