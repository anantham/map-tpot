export default function CommunitiesTopBar({
  communities,
  reviewer,
  egoInput,
  onEgoInputChange,
  onEgoCommit,
  egoAccountId,
  queueLoading = false,
  onNextGoldCandidate,
}) {
  return (
    <div style={{
      padding: '10px 16px',
      borderBottom: '1px solid var(--panel-border, #1e293b)',
      display: 'flex',
      alignItems: 'center',
      gap: 12,
    }}>
      <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Communities</h2>
      <div style={{ fontSize: 12, color: '#64748b' }}>
        {communities.length} communities · {communities.reduce((sum, community) => sum + community.member_count, 0)} members
      </div>
      <div style={{
        fontSize: 12,
        padding: '2px 8px',
        borderRadius: 999,
        background: 'rgba(59,130,246,0.12)',
        color: '#93c5fd',
      }}>
        gold reviewer: {reviewer}
      </div>
      <button
        onClick={onNextGoldCandidate}
        disabled={queueLoading || !onNextGoldCandidate}
        style={{
          padding: '6px 10px',
          fontSize: 12,
          fontWeight: 700,
          borderRadius: 6,
          border: '1px solid var(--panel-border, #2d3748)',
          background: queueLoading ? 'rgba(59,130,246,0.18)' : 'rgba(59,130,246,0.12)',
          color: queueLoading ? '#dbeafe' : '#93c5fd',
          cursor: queueLoading ? 'wait' : 'pointer',
        }}
      >
        {queueLoading ? 'Loading Queue...' : 'Next Gold Candidate'}
      </button>
      <div style={{ flex: 1 }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
        <span style={{ color: '#64748b' }}>ego:</span>
        <input
          type="text"
          value={egoInput}
          onChange={(event) => onEgoInputChange(event.target.value)}
          onBlur={onEgoCommit}
          onKeyDown={(event) => {
            if (event.key === 'Enter') onEgoCommit()
          }}
          placeholder="@handle"
          style={{
            width: 140,
            padding: '4px 8px',
            background: 'var(--bg, #0f172a)',
            border: '1px solid var(--panel-border, #2d3748)',
            borderRadius: 4,
            color: 'var(--text, #e2e8f0)',
            fontSize: 12,
          }}
        />
        {egoAccountId && <span style={{ color: '#22c55e', fontSize: 11 }}>✓</span>}
      </div>
    </div>
  )
}
