export default function AccountPreviewHeader({
  accountId,
  profile,
  tpotScore,
  tpotScoreMax,
  onBack,
  onToggleSettings,
}) {
  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 4 }}>
        <button onClick={onBack} style={{
          background: 'none',
          border: 'none',
          color: '#3b82f6',
          cursor: 'pointer',
          fontSize: 14,
          padding: 0,
        }}>
          ← Back
        </button>
        <div style={{ flex: 1 }} />
        <button onClick={onToggleSettings} style={{
          background: 'none',
          border: '1px solid var(--panel-border, #2d3748)',
          borderRadius: 4,
          color: '#64748b',
          cursor: 'pointer',
          fontSize: 12,
          padding: '4px 8px',
        }}>
          Sections
        </button>
      </div>

      <div style={{ marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <span style={{ fontSize: 20, fontWeight: 700 }}>
            @{profile.username || accountId.slice(0, 8)}
          </span>
          {profile.display_name && (
            <span style={{ fontSize: 14, color: '#94a3b8' }}>{profile.display_name}</span>
          )}
          <span style={{
            fontSize: 12,
            padding: '2px 8px',
            borderRadius: 10,
            background: 'rgba(59,130,246,0.15)',
            color: '#3b82f6',
            fontWeight: 600,
          }}>
            TPOT {tpotScore}/{tpotScoreMax}
          </span>
        </div>
        {profile.bio && (
          <div style={{ fontSize: 13, color: '#94a3b8', marginTop: 6, lineHeight: 1.5 }}>
            {profile.bio}
          </div>
        )}
        <div style={{ marginTop: 6, display: 'flex', gap: 12, fontSize: 12 }}>
          {profile.username && (
            <a
              href={`https://x.com/${profile.username}`}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: '#3b82f6' }}
            >
              Open on X →
            </a>
          )}
          {profile.location && <span style={{ color: '#64748b' }}>{profile.location}</span>}
        </div>
      </div>
    </>
  )
}
