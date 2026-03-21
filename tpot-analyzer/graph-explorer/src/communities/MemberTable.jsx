export default function MemberTable({
  members,
  onSelectAccount,
  showFollowOnly,
  onToggleFollowOnly,
  searchQuery,
  onSearchChange,
}) {
  const filtered = members.filter((member) => {
    if (showFollowOnly && !member.i_follow) return false
    if (searchQuery && !member.username?.toLowerCase().includes(searchQuery.toLowerCase())) return false
    return true
  })

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0 }}>
      <div style={{
        display: 'flex',
        gap: 8,
        padding: '8px 12px',
        alignItems: 'center',
        borderBottom: '1px solid var(--panel-border, #1e293b)',
        flexShrink: 0,
      }}>
        <input
          type="text"
          placeholder="Search @handle..."
          value={searchQuery}
          onChange={(event) => onSearchChange(event.target.value)}
          style={{
            flex: 1,
            padding: '6px 10px',
            background: 'var(--bg, #0f172a)',
            border: '1px solid var(--panel-border, #2d3748)',
            borderRadius: 6,
            color: 'var(--text, #e2e8f0)',
            fontSize: 13,
          }}
        />
        <button
          onClick={onToggleFollowOnly}
          style={{
            padding: '6px 12px',
            fontSize: 12,
            fontWeight: 600,
            border: '1px solid var(--panel-border, #2d3748)',
            borderRadius: 6,
            background: showFollowOnly ? 'var(--accent, #3b82f6)' : 'transparent',
            color: showFollowOnly ? '#fff' : 'var(--text, #e2e8f0)',
            cursor: 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          ★ I follow
        </button>
        <span style={{ fontSize: 12, color: '#64748b', whiteSpace: 'nowrap' }}>
          {filtered.length}/{members.length}
        </span>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{
              borderBottom: '1px solid var(--panel-border, #1e293b)',
              color: '#64748b',
              fontSize: 11,
              textTransform: 'uppercase',
            }}>
              <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600 }}>Account</th>
              <th style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, width: 60 }}>Weight</th>
              <th style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 600, width: 60 }}>Source</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((member) => (
              <tr
                key={member.account_id}
                onClick={() => onSelectAccount(member)}
                style={{
                  cursor: 'pointer',
                  borderBottom: '1px solid var(--panel-border, #0f172a)',
                }}
              >
                <td style={{ padding: '8px 12px' }}>
                  <span style={{ fontWeight: 500 }}>@{member.username || member.account_id.slice(0, 8)}</span>
                  {member.i_follow && (
                    <span
                      style={{ marginLeft: 6, fontSize: 11, color: '#f59e0b' }}
                      title="You follow this account"
                    >
                      ★
                    </span>
                  )}
                  {member.bio && (
                    <div style={{
                      fontSize: 11,
                      color: '#64748b',
                      marginTop: 2,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      maxWidth: 400,
                    }}>
                      {member.bio}
                    </div>
                  )}
                </td>
                <td style={{ padding: '8px 12px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                  {(member.weight * 100).toFixed(0)}%
                </td>
                <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                  <span style={{
                    fontSize: 10,
                    fontWeight: 700,
                    padding: '2px 6px',
                    borderRadius: 4,
                    background: member.source === 'human' ? 'rgba(34,197,94,0.15)' : 'rgba(148,163,184,0.15)',
                    color: member.source === 'human' ? '#22c55e' : '#94a3b8',
                  }}>
                    {member.source === 'human' ? 'HUMAN' : 'NMF'}
                  </span>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={3} style={{ padding: 24, textAlign: 'center', color: '#64748b' }}>
                  {members.length === 0 ? 'No members' : 'No matches'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
