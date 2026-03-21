import { formatMetric } from './goldLabelUtils'

export default function GoldScorecard({
  evaluationSplit,
  onEvaluationSplitChange,
  scorecard,
  scorecardLoading,
  scorecardError,
}) {
  const scoredMethods = Object.entries(scorecard?.community?.methods || {}).sort((left, right) => {
    const leftAuc = left[1]?.metrics?.aucPr ?? -1
    const rightAuc = right[1]?.metrics?.aucPr ?? -1
    return rightAuc - leftAuc
  })

  return (
    <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--panel-border, #2d3748)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>
          Evaluator
        </span>
        <select
          value={evaluationSplit}
          onChange={(event) => onEvaluationSplitChange(event.target.value)}
          style={{
            padding: '4px 6px',
            fontSize: 12,
            background: 'var(--bg, #0f172a)',
            border: '1px solid var(--panel-border, #2d3748)',
            borderRadius: 4,
            color: 'var(--text, #e2e8f0)',
          }}
        >
          <option value="dev">dev</option>
          <option value="test">test</option>
        </select>
      </div>

      {scorecardLoading && <div style={{ fontSize: 12, color: '#64748b' }}>Loading evaluator metrics...</div>}
      {!scorecardLoading && scorecardError && <div style={{ fontSize: 12, color: '#f59e0b' }}>{scorecardError}</div>}
      {!scorecardLoading && !scorecardError && scorecard?.community && (
        <>
          <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 8 }}>
            best method: {scorecard.bestMethodByMacroAucPr || 'n/a'}
          </div>
          <div style={{ display: 'grid', gap: 6 }}>
            {scoredMethods.map(([methodId, method]) => (
              <div
                key={methodId}
                style={{
                  padding: '8px 10px',
                  borderRadius: 6,
                  border: '1px solid var(--panel-border, #2d3748)',
                  background: 'rgba(15,23,42,0.35)',
                  fontSize: 12,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontWeight: 700 }}>{methodId}</span>
                  <span style={{ color: method.available ? '#86efac' : '#f59e0b' }}>
                    {method.available ? 'available' : method.reason || 'unavailable'}
                  </span>
                </div>
                {method.metrics && (
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', color: '#cbd5e1' }}>
                    <span>AUC-PR {formatMetric(method.metrics.aucPr)}</span>
                    <span>F1 {formatMetric(method.metrics.f1)}</span>
                    <span>Brier {formatMetric(method.metrics.brier, 3)}</span>
                    <span>ECE {formatMetric(method.metrics.ece, 3)}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
