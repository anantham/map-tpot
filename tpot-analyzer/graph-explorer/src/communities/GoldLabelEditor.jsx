import { formatPct, JUDGMENT_OPTIONS, judgmentButtonStyle } from './goldLabelUtils'

export default function GoldLabelEditor({
  reviewer,
  split,
  currentLabel,
  targetCommunityId,
  communityOptions,
  onTargetCommunityChange,
  judgment,
  onJudgmentChange,
  confidencePct,
  onConfidenceChange,
  note,
  onNoteChange,
  canonicalWeight,
  canonicalSource,
  saving,
  onSave,
  onClear,
  onRequestNextCandidate,
  queueLoading = false,
  labelsError,
}) {
  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 12, color: '#64748b' }}>reviewer</span>
          <span style={{
            fontSize: 12,
            fontWeight: 600,
            padding: '2px 8px',
            borderRadius: 999,
            background: 'rgba(59,130,246,0.15)',
            color: '#93c5fd',
          }}>
            {reviewer || 'human'}
          </span>
          <span style={{
            fontSize: 12,
            fontWeight: 600,
            padding: '2px 8px',
            borderRadius: 999,
            background: 'rgba(15,23,42,0.7)',
            color: split ? '#e2e8f0' : '#64748b',
            border: '1px solid var(--panel-border, #2d3748)',
          }}>
            {split ? `split: ${split}` : 'split assigned on first save'}
          </span>
        </div>
        {currentLabel && (
          <span style={{ fontSize: 12, fontWeight: 700, color: '#e2e8f0' }}>
            current: {currentLabel.judgment.toUpperCase()}
          </span>
        )}
      </div>

      <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4 }}>
        Target community
      </label>
      <select
        value={targetCommunityId}
        onChange={(event) => onTargetCommunityChange(event.target.value)}
        style={{
          width: '100%',
          padding: '6px 8px',
          marginBottom: 10,
          background: 'var(--bg, #0f172a)',
          border: '1px solid var(--panel-border, #2d3748)',
          borderRadius: 6,
          color: 'var(--text, #e2e8f0)',
        }}
      >
        {communityOptions.map((community) => (
          <option key={community.id} value={community.id}>{community.name}</option>
        ))}
      </select>

      <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
        {JUDGMENT_OPTIONS.map((option) => (
          <button
            key={option.id}
            onClick={() => onJudgmentChange(option.id)}
            style={judgmentButtonStyle(option.id, judgment, option.color)}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 12, color: '#64748b', minWidth: 70 }}>confidence</span>
        <input
          type="range"
          min={0}
          max={100}
          value={confidencePct}
          onChange={(event) => onConfidenceChange(Number(event.target.value))}
          style={{ flex: 1, accentColor: '#3b82f6' }}
        />
        <input
          type="number"
          min={0}
          max={100}
          value={confidencePct}
          onChange={(event) => onConfidenceChange(Math.max(0, Math.min(100, Number(event.target.value))))}
          style={{
            width: 56,
            padding: '4px 6px',
            textAlign: 'right',
            background: 'var(--bg, #0f172a)',
            border: '1px solid var(--panel-border, #2d3748)',
            borderRadius: 4,
            color: 'var(--text, #e2e8f0)',
          }}
        />
      </div>

      <div style={{ display: 'flex', gap: 10, marginBottom: 10, fontSize: 12, color: '#94a3b8', flexWrap: 'wrap' }}>
        <span>canonical weight: {canonicalWeight != null ? formatPct(canonicalWeight) : 'n/a'}</span>
        <span>canonical source: {canonicalSource || 'n/a'}</span>
      </div>

      <textarea
        value={note}
        onChange={(event) => onNoteChange(event.target.value)}
        placeholder="Why is this a gold example?"
        rows={3}
        style={{
          width: '100%',
          padding: 8,
          fontSize: 13,
          lineHeight: 1.5,
          boxSizing: 'border-box',
          background: 'var(--bg, #0f172a)',
          border: '1px solid var(--panel-border, #2d3748)',
          borderRadius: 6,
          color: 'var(--text, #e2e8f0)',
          resize: 'vertical',
        }}
      />

      <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
        <button
          onClick={onSave}
          disabled={saving || !targetCommunityId}
          style={{
            flex: 1,
            padding: '6px 12px',
            fontSize: 12,
            fontWeight: 700,
            background: '#22c55e',
            color: '#fff',
            border: 'none',
            borderRadius: 6,
            cursor: saving ? 'wait' : 'pointer',
          }}
        >
          {saving ? 'Saving...' : 'Save Gold Label'}
        </button>
        <button
          onClick={onClear}
          disabled={saving || !currentLabel}
          style={{
            padding: '6px 12px',
            fontSize: 12,
            fontWeight: 700,
            background: 'transparent',
            color: currentLabel ? '#f87171' : '#64748b',
            border: '1px solid var(--panel-border, #2d3748)',
            borderRadius: 6,
            cursor: currentLabel ? 'pointer' : 'not-allowed',
          }}
        >
          Clear
        </button>
        <button
          onClick={onRequestNextCandidate}
          disabled={saving || queueLoading || !onRequestNextCandidate}
          style={{
            padding: '6px 12px',
            fontSize: 12,
            fontWeight: 700,
            background: 'rgba(59,130,246,0.12)',
            color: onRequestNextCandidate ? '#93c5fd' : '#64748b',
            border: '1px solid var(--panel-border, #2d3748)',
            borderRadius: 6,
            cursor: queueLoading ? 'wait' : (onRequestNextCandidate ? 'pointer' : 'not-allowed'),
          }}
        >
          {queueLoading ? 'Loading...' : 'Next Candidate'}
        </button>
      </div>

      {labelsError && <div style={{ marginTop: 10, fontSize: 12, color: '#f87171' }}>{labelsError}</div>}
    </>
  )
}
