import MemberTable from './MemberTable'

export default function SelectedCommunityPanel({
  selectedCommunity,
  editingName,
  setEditingName,
  editingDesc,
  setEditingDesc,
  onUpdateCommunity,
  membersLoading,
  members,
  onSelectAccount,
  showFollowOnly,
  onToggleFollowOnly,
  searchQuery,
  onSearchChange,
}) {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      {selectedCommunity && (
        <>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '8px 12px',
            borderBottom: '1px solid var(--panel-border, #1e293b)',
          }}>
            <span
              style={{
                width: 16,
                height: 16,
                borderRadius: '50%',
                background: selectedCommunity.color || '#64748b',
                border: '1px solid rgba(255,255,255,0.1)',
                cursor: 'pointer',
              }}
              title="Click to edit color"
              onClick={() => {
                const next = window.prompt('Community color (hex)', selectedCommunity.color || '#64748b')
                if (next && next !== selectedCommunity.color) onUpdateCommunity({ color: next })
              }}
            />
            {editingName !== null ? (
              <input
                autoFocus
                value={editingName}
                onChange={(event) => setEditingName(event.target.value)}
                onBlur={() => {
                  if (editingName && editingName !== selectedCommunity.name) {
                    onUpdateCommunity({ name: editingName })
                  } else {
                    setEditingName(null)
                  }
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') event.target.blur()
                  if (event.key === 'Escape') setEditingName(null)
                }}
                style={{
                  flex: 1,
                  padding: '4px 8px',
                  fontSize: 14,
                  fontWeight: 600,
                  background: 'var(--bg, #0f172a)',
                  border: '1px solid var(--accent, #3b82f6)',
                  borderRadius: 4,
                  color: 'var(--text, #e2e8f0)',
                }}
              />
            ) : (
              <span
                onClick={() => setEditingName(selectedCommunity.name)}
                style={{ fontSize: 14, fontWeight: 600, cursor: 'pointer' }}
                title="Click to rename"
              >
                {selectedCommunity.name}
              </span>
            )}
            <span style={{ fontSize: 11, color: '#64748b' }}>
              {selectedCommunity.member_count} members
            </span>
          </div>

          <div style={{ padding: '4px 12px', borderBottom: '1px solid var(--panel-border, #1e293b)' }}>
            {editingDesc !== null ? (
              <input
                autoFocus
                value={editingDesc}
                onChange={(event) => setEditingDesc(event.target.value)}
                onBlur={() => {
                  if (editingDesc !== (selectedCommunity.description || '')) {
                    onUpdateCommunity({ description: editingDesc || null })
                  } else {
                    setEditingDesc(null)
                  }
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') event.target.blur()
                  if (event.key === 'Escape') setEditingDesc(null)
                }}
                placeholder="Add a description..."
                style={{
                  width: '100%',
                  padding: '4px 8px',
                  fontSize: 12,
                  background: 'var(--bg, #0f172a)',
                  border: '1px solid var(--accent, #3b82f6)',
                  borderRadius: 4,
                  color: 'var(--text, #e2e8f0)',
                  boxSizing: 'border-box',
                }}
              />
            ) : (
              <span
                onClick={() => setEditingDesc(selectedCommunity.description || '')}
                style={{
                  fontSize: 12,
                  cursor: 'pointer',
                  color: selectedCommunity.description ? 'var(--text, #e2e8f0)' : '#475569',
                  fontStyle: selectedCommunity.description ? 'normal' : 'italic',
                }}
                title="Click to edit description"
              >
                {selectedCommunity.description || 'Add a description...'}
              </span>
            )}
          </div>
        </>
      )}

      {membersLoading ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b' }}>
          Loading members...
        </div>
      ) : (
        <MemberTable
          members={members}
          onSelectAccount={onSelectAccount}
          showFollowOnly={showFollowOnly}
          onToggleFollowOnly={onToggleFollowOnly}
          searchQuery={searchQuery}
          onSearchChange={onSearchChange}
        />
      )}
    </div>
  )
}
