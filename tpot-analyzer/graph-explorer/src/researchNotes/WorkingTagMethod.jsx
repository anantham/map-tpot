const observedFraction = value => value !== null && value !== undefined && Number.isFinite(Number(value))
  ? `${(Number(value) * 100).toFixed(1)}%` : 'unknown'

export default function WorkingTagMethod({ result, tagKind }) {
  const diagnostics = result.diagnostics || {}
  const reachability = diagnostics.observedAnchorReachability || {}
  const pairLinks = diagnostics.observedPositivePairLinks || {}
  const boundaryCrossing = diagnostics.observedBoundaryCrossing || {}
  const posts = result.semantics?.channel === 'post_references'
  const savedApi = result.semantics?.channel === 'saved_api_refs'
  return <details className="working-tag-method">
    <summary>How this ranking was calculated</summary>
    {tagKind && <p className="working-tag-kind">Tag kind: {tagKind.replaceAll('_',' ')}.
      This is retrieval evidence, not proof of social affiliation or competence.</p>}
    <p className="working-tag-semantics">{result.semantics?.scoreMeaning || 'Uncalibrated ranking signal'}.
      No calibrated confidence is computed. {result.semantics?.rawSupportTies}</p>
    {savedApi ? <>
      <p>Historical saved API references: {result.semantics?.recencyMeaning || 'All-time saved references; no recent-activity filter.'}</p>
      <p>Saved-reference method: {result.semantics?.method || 'unknown'}.</p>
      <p>{result.semantics?.edgeBoundary}</p>
      <p>{result.semantics?.generalization}</p>
      <p>Source status: {result.source?.status || 'unknown'}; typed pairs: {result.source?.coverage?.typedPairs ?? 'unknown'}; post observations: {result.source?.coverage?.postObservations ?? 'unknown'}; source accounts: {result.source?.coverage?.sourceAccounts ?? 'unknown'}.</p>
      <p>Source totals include self references and can count a post under several targets/types; discovery excludes self links. Repeated captures do not add support.</p>
      <p>Candidate diagnostics: {diagnostics.candidateCount ?? 'unknown'} candidates, {diagnostics.returnedCount ?? 'unknown'} returned, {diagnostics.referenceCandidateCount ?? 'unknown'} linked to IN or NOT IN examples before the support filter. Counts cover the selected search scope, not only visible cards.</p>
      <p>NOT IN links are context, not a penalty. The ordering is uncalibrated and is not a confidence score.</p>
    </> : posts ? <>
      <p>{result.semantics.recencyMeaning}</p>
      <p>{result.semantics.edgeBoundary}</p>
      <p>{result.semantics.generalization}</p>
      <p>Already judged accounts are excluded for this exact curator/tag. Up to three
        IN examples have source-post paths shown per candidate; additional support
        is included in the count. NOT IN links are context, not a negative label.</p>
      <p>Publication {result.source?.exportId}. Cutoff {result.filters?.latestSince || 'none'}.
        Candidate changes reflect the current examples and filters, not a frozen evaluation.</p>
    </> : <>
      <div className="working-tag-topology">
        <strong>Observed graph structure — not cluster confidence</strong>
        <span>IN examples reached by other IN examples:{' '}
          {reachability.positiveAnchorsReachedByPositive || 0}/{reachability.eligiblePositiveAnchors || 0}
          {' '}({observedFraction(reachability.observedFraction)})</span>
        <span>Directed links among IN examples: {pairLinks.observedDirectedEdges || 0}/{pairLinks.possibleDirectedEdges || 0}
          {' '}({observedFraction(pairLinks.observedFraction)})</span>
        <span>NOT IN examples reached: {boundaryCrossing.negativeAnchorsReachedByPositive || 0}/{boundaryCrossing.eligibleNegativeAnchors || 0}
          {' '}({observedFraction(boundaryCrossing.observedFraction)})</span>
        <span>{diagnostics.semantics?.missingness || 'Unobserved edges are unknown, not confirmed absences.'}
          {' '}No held-out recovery or cluster-existence claim is made.</span>
      </div>
      <p className="working-tag-channel">Stored-follow channel only. Typed engagement and post content are not included yet.</p>
    </>}
  </details>
}
