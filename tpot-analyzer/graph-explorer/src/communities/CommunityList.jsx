export default function CommunityList({ communities, selectedId, onSelect }) {
  return (
    <div style={{
      width: 240,
      borderRight: '1px solid var(--panel-border, #1e293b)',
      overflowY: 'auto',
      padding: '12px 0',
      flexShrink: 0,
    }}>
      <div style={{
        padding: '0 12px 8px',
        fontSize: 11,
        fontWeight: 700,
        color: '#64748b',
        textTransform: 'uppercase',
      }}>
        Communities ({communities.length})
      </div>
      {communities.map((community) => (
        <button
          key={community.id}
          onClick={() => onSelect(community)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            width: '100%',
            padding: '8px 12px',
            border: 'none',
            background: selectedId === community.id ? 'var(--accent-dim, rgba(59,130,246,0.15))' : 'transparent',
            color: 'var(--text, #e2e8f0)',
            cursor: 'pointer',
            textAlign: 'left',
            fontSize: 13,
          }}
        >
          <span style={{
            width: 10,
            height: 10,
            borderRadius: '50%',
            background: community.color || '#64748b',
            flexShrink: 0,
          }} />
          <span style={{
            flex: 1,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            fontWeight: selectedId === community.id ? 600 : 400,
          }}>
            {community.name}
          </span>
          <span style={{ fontSize: 11, color: '#64748b', flexShrink: 0 }}>
            {community.member_count}
          </span>
        </button>
      ))}
    </div>
  )
}
