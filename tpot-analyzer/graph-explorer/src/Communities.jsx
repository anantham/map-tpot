/**
 * Communities — Account community curation dashboard.
 *
 * Layout: [community list | center panel]
 * Center panel switches between:
 *   - MemberTable: list of members with search/filter
 *   - AccountDeepDive: full preview with signals, weights, notes
 */
import { useState, useEffect, useCallback } from 'react'
import {
  fetchCommunities,
  fetchCommunityMembers,
  updateCommunity,
  fetchBranches,
  createBranch,
  switchBranch,
  saveSnapshot,
  checkBranchDirty,
} from './communitiesApi'
import { searchAccounts } from './accountsApi'
import AccountDeepDive from './AccountDeepDive'


function CommunityList({ communities, selectedId, onSelect }) {
  return (
    <div style={{
      width: 240, borderRight: '1px solid var(--panel-border, #1e293b)',
      overflowY: 'auto', padding: '12px 0', flexShrink: 0,
    }}>
      <div style={{ padding: '0 12px 8px', fontSize: 11, fontWeight: 700,
        color: '#64748b', textTransform: 'uppercase' }}>
        Communities ({communities.length})
      </div>
      {communities.map(c => (
        <button
          key={c.id}
          onClick={() => onSelect(c)}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            width: '100%', padding: '8px 12px', border: 'none',
            background: selectedId === c.id ? 'var(--accent-dim, rgba(59,130,246,0.15))' : 'transparent',
            color: 'var(--text, #e2e8f0)', cursor: 'pointer',
            textAlign: 'left', fontSize: 13,
          }}
        >
          <span style={{
            width: 10, height: 10, borderRadius: '50%',
            background: c.color || '#64748b', flexShrink: 0,
          }} />
          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis',
            whiteSpace: 'nowrap', fontWeight: selectedId === c.id ? 600 : 400 }}>
            {c.name}
          </span>
          <span style={{ fontSize: 11, color: '#64748b', flexShrink: 0 }}>
            {c.member_count}
          </span>
        </button>
      ))}
    </div>
  )
}


function MemberTable({ members, onSelectAccount, showFollowOnly,
  onToggleFollowOnly, searchQuery, onSearchChange }) {
  const filtered = members.filter(m => {
    if (showFollowOnly && !m.i_follow) return false
    if (searchQuery && !m.username?.toLowerCase().includes(searchQuery.toLowerCase())) return false
    return true
  })

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0 }}>
      <div style={{
        display: 'flex', gap: 8, padding: '8px 12px', alignItems: 'center',
        borderBottom: '1px solid var(--panel-border, #1e293b)',
        flexShrink: 0,
      }}>
        <input
          type="text" placeholder="Search @handle..."
          value={searchQuery} onChange={e => onSearchChange(e.target.value)}
          style={{
            flex: 1, padding: '6px 10px', background: 'var(--bg, #0f172a)',
            border: '1px solid var(--panel-border, #2d3748)', borderRadius: 6,
            color: 'var(--text, #e2e8f0)', fontSize: 13,
          }}
        />
        <button
          onClick={onToggleFollowOnly}
          style={{
            padding: '6px 12px', fontSize: 12, fontWeight: 600,
            border: '1px solid var(--panel-border, #2d3748)', borderRadius: 6,
            background: showFollowOnly ? 'var(--accent, #3b82f6)' : 'transparent',
            color: showFollowOnly ? '#fff' : 'var(--text, #e2e8f0)',
            cursor: 'pointer', whiteSpace: 'nowrap',
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
            <tr style={{ borderBottom: '1px solid var(--panel-border, #1e293b)',
              color: '#64748b', fontSize: 11, textTransform: 'uppercase' }}>
              <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600 }}>Account</th>
              <th style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, width: 60 }}>Weight</th>
              <th style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 600, width: 60 }}>Source</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(m => (
              <tr
                key={m.account_id}
                onClick={() => onSelectAccount(m)}
                style={{
                  cursor: 'pointer',
                  borderBottom: '1px solid var(--panel-border, #0f172a)',
                }}
              >
                <td style={{ padding: '8px 12px' }}>
                  <span style={{ fontWeight: 500 }}>@{m.username || m.account_id.slice(0, 8)}</span>
                  {m.i_follow && (
                    <span style={{ marginLeft: 6, fontSize: 11, color: '#f59e0b' }}
                      title="You follow this account">★</span>
                  )}
                  {m.bio && (
                    <div style={{ fontSize: 11, color: '#64748b', marginTop: 2,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      maxWidth: 400 }}>
                      {m.bio}
                    </div>
                  )}
                </td>
                <td style={{ padding: '8px 12px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                  {(m.weight * 100).toFixed(0)}%
                </td>
                <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                  <span style={{
                    fontSize: 10, fontWeight: 700, padding: '2px 6px', borderRadius: 4,
                    background: m.source === 'human' ? 'rgba(34,197,94,0.15)' : 'rgba(148,163,184,0.15)',
                    color: m.source === 'human' ? '#22c55e' : '#94a3b8',
                  }}>
                    {m.source === 'human' ? 'HUMAN' : 'NMF'}
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


export default function Communities({ ego: defaultEgo }) {
  const [communities, setCommunities] = useState([])
  const [selectedCommunity, setSelectedCommunity] = useState(null)
  const [members, setMembers] = useState([])

  // Navigation: null = member list, account_id = deep dive
  const [deepDiveAccountId, setDeepDiveAccountId] = useState(null)

  const [loading, setLoading] = useState(true)
  const [membersLoading, setMembersLoading] = useState(false)
  const [error, setError] = useState(null)
  const [showFollowOnly, setShowFollowOnly] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [editingName, setEditingName] = useState(null)
  const [editingColor, setEditingColor] = useState(null)
  const [editingDesc, setEditingDesc] = useState(null)

  const [ego, setEgo] = useState(defaultEgo || '')
  const [egoInput, setEgoInput] = useState(defaultEgo || '')
  const [egoAccountId, setEgoAccountId] = useState(null)

  // Branch state
  const [branches, setBranches] = useState([])
  const [activeBranch, setActiveBranch] = useState(null)
  const [isDirty, setIsDirty] = useState(false)
  const [showBranchModal, setShowBranchModal] = useState(false) // 'switch-confirm' | 'new-branch' | false
  const [pendingSwitchId, setPendingSwitchId] = useState(null)
  const [newBranchName, setNewBranchName] = useState('')

  useEffect(() => {
    if (!ego) { setEgoAccountId(null); return }
    searchAccounts({ q: ego, limit: 1 })
      .then(results => {
        const match = Array.isArray(results) ? results[0] : null
        if (match && match.username?.toLowerCase() === ego.toLowerCase()) {
          setEgoAccountId(match.id)
        } else {
          setEgoAccountId(null)
        }
      })
      .catch(() => setEgoAccountId(null))
  }, [ego])

  // Branch loading
  const loadBranches = useCallback(async () => {
    try {
      const data = await fetchBranches()
      setBranches(data)
      const active = data.find(b => b.is_active)
      setActiveBranch(active || null)
      if (active) {
        const dirtyResult = await checkBranchDirty(active.id)
        setIsDirty(dirtyResult.dirty)
      }
    } catch (e) { setError(e.message) }
  }, [])

  const refreshDirtyState = useCallback(async () => {
    if (!activeBranch) return
    try {
      const result = await checkBranchDirty(activeBranch.id)
      setIsDirty(result.dirty)
    } catch { /* ignore polling errors */ }
  }, [activeBranch])

  const handleSwitchBranch = useCallback(async (branchId, action) => {
    try {
      await switchBranch(branchId, action)
      await loadBranches()
      const comms = await fetchCommunities()
      setCommunities(comms)
      if (comms.length > 0) setSelectedCommunity(comms[0])
      setMembers([])
      setDeepDiveAccountId(null)
      setShowBranchModal(false)
      setPendingSwitchId(null)
    } catch (e) { setError(e.message) }
  }, [loadBranches])

  const handleCreateBranch = useCallback(async () => {
    if (!newBranchName.trim()) return
    try {
      await createBranch(newBranchName.trim())
      setNewBranchName('')
      setShowBranchModal(false)
      await loadBranches()
      const comms = await fetchCommunities()
      setCommunities(comms)
      if (comms.length > 0) setSelectedCommunity(comms[0])
    } catch (e) { setError(e.message) }
  }, [newBranchName, loadBranches])

  const handleSaveSnapshot = useCallback(async () => {
    if (!activeBranch) return
    try {
      const name = window.prompt('Snapshot name (optional):')
      await saveSnapshot(activeBranch.id, name || undefined)
      setIsDirty(false)
      await loadBranches()
    } catch (e) { setError(e.message) }
  }, [activeBranch, loadBranches])

  const initiateSwitch = useCallback(async (branchId) => {
    if (!activeBranch || branchId === activeBranch.id) return
    if (isDirty) {
      setPendingSwitchId(branchId)
      setShowBranchModal('switch-confirm')
    } else {
      await handleSwitchBranch(branchId, 'discard')
    }
  }, [activeBranch, isDirty, handleSwitchBranch])

  useEffect(() => { loadBranches() }, [loadBranches])

  useEffect(() => {
    setLoading(true)
    fetchCommunities()
      .then(data => {
        setCommunities(data)
        if (data.length > 0) setSelectedCommunity(data[0])
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const loadMembers = useCallback(() => {
    if (!selectedCommunity) return
    setMembersLoading(true)
    setDeepDiveAccountId(null)
    setSearchQuery('')
    fetchCommunityMembers(selectedCommunity.id, { ego: egoAccountId })
      .then(data => setMembers(data.members || []))
      .catch(e => setError(e.message))
      .finally(() => setMembersLoading(false))
  }, [selectedCommunity?.id, egoAccountId])

  useEffect(() => { loadMembers() }, [loadMembers])

  const handleUpdateCommunity = useCallback(async (updates) => {
    if (!selectedCommunity) return
    try {
      const result = await updateCommunity(selectedCommunity.id, updates)
      const updated = { ...selectedCommunity, ...result }
      setSelectedCommunity(updated)
      setCommunities(prev => prev.map(c => c.id === updated.id ? { ...c, ...result } : c))
      setEditingName(null)
      refreshDirtyState()
    } catch (e) { setError(e.message) }
  }, [selectedCommunity, refreshDirtyState])

  const handleWeightsChanged = useCallback(async () => {
    // Refresh member list + community counts after weight edit
    loadMembers()
    const comms = await fetchCommunities()
    setCommunities(comms)
    refreshDirtyState()
  }, [loadMembers, refreshDirtyState])

  if (loading) return (
    <div style={{ height: '100%', display: 'flex', alignItems: 'center',
      justifyContent: 'center', color: '#64748b' }}>
      Loading communities...
    </div>
  )

  return (
    <div style={{
      height: '100%', display: 'flex', flexDirection: 'column',
      background: 'var(--bg, #0f172a)', color: 'var(--text, #e2e8f0)',
    }}>
      {/* Header */}
      <div style={{
        padding: '10px 16px', borderBottom: '1px solid var(--panel-border, #1e293b)',
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Communities</h2>
        <div style={{ fontSize: 12, color: '#64748b' }}>
          {communities.length} communities · {communities.reduce((s, c) => s + c.member_count, 0)} members
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
          <span style={{ color: '#64748b' }}>ego:</span>
          <input
            type="text" value={egoInput}
            onChange={e => setEgoInput(e.target.value)}
            onBlur={() => setEgo(egoInput)}
            onKeyDown={e => e.key === 'Enter' && setEgo(egoInput)}
            placeholder="@handle"
            style={{
              width: 140, padding: '4px 8px',
              background: 'var(--bg, #0f172a)',
              border: '1px solid var(--panel-border, #2d3748)',
              borderRadius: 4, color: 'var(--text, #e2e8f0)', fontSize: 12,
            }}
          />
          {egoAccountId && <span style={{ color: '#22c55e', fontSize: 11 }}>✓</span>}
        </div>
      </div>

      {error && (
        <div style={{
          padding: '8px 16px', background: 'rgba(239,68,68,0.1)',
          color: '#f87171', fontSize: 13, display: 'flex', alignItems: 'center',
        }}>
          <span style={{ flex: 1 }}>{error}</span>
          <button onClick={() => setError(null)}
            style={{ background: 'none', border: 'none',
              color: '#f87171', cursor: 'pointer', fontSize: 16 }}>
            ×
          </button>
        </div>
      )}

      {/* Branch bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 16px',
        borderBottom: '1px solid var(--panel-border, #1e293b)',
        background: 'var(--panel, #1e293b)',
        fontSize: 12, flexShrink: 0,
      }}>
        <span style={{ color: '#64748b', fontWeight: 600 }}>Branch:</span>
        <select
          value={activeBranch?.id || ''}
          onChange={e => initiateSwitch(e.target.value)}
          style={{
            padding: '4px 8px', fontSize: 12,
            background: 'var(--bg, #0f172a)',
            border: '1px solid var(--panel-border, #2d3748)',
            borderRadius: 4, color: 'var(--text, #e2e8f0)',
          }}
        >
          {branches.map(b => (
            <option key={b.id} value={b.id}>
              {b.name} ({b.snapshot_count} saves)
            </option>
          ))}
        </select>
        <button onClick={handleSaveSnapshot} style={{
          padding: '4px 10px', fontSize: 12, fontWeight: 600,
          background: '#22c55e', color: '#fff', border: 'none',
          borderRadius: 4, cursor: 'pointer',
        }}>
          Save
        </button>
        <button onClick={() => setShowBranchModal('new-branch')} style={{
          padding: '4px 10px', fontSize: 12, fontWeight: 600,
          background: '#3b82f6', color: '#fff', border: 'none',
          borderRadius: 4, cursor: 'pointer',
        }}>
          Branch...
        </button>
        {isDirty && (
          <span style={{ color: '#f59e0b', fontWeight: 600 }}>
            unsaved changes
          </span>
        )}
      </div>

      {/* Switch confirmation modal */}
      {showBranchModal === 'switch-confirm' && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 1000,
        }}>
          <div style={{
            background: 'var(--panel, #1e293b)', borderRadius: 8,
            padding: 24, maxWidth: 400, width: '90%',
            border: '1px solid var(--panel-border, #2d3748)',
          }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>
              Unsaved changes on &ldquo;{activeBranch?.name}&rdquo;
            </div>
            <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 16 }}>
              Save your changes before switching, or discard them?
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button onClick={() => { setShowBranchModal(false); setPendingSwitchId(null) }}
                style={{ padding: '6px 16px', fontSize: 12, background: 'transparent',
                  border: '1px solid var(--panel-border, #2d3748)', borderRadius: 4,
                  color: 'var(--text, #e2e8f0)', cursor: 'pointer' }}>
                Cancel
              </button>
              <button onClick={() => handleSwitchBranch(pendingSwitchId, 'discard')}
                style={{ padding: '6px 16px', fontSize: 12, background: '#ef4444',
                  color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}>
                Discard
              </button>
              <button onClick={() => handleSwitchBranch(pendingSwitchId, 'save')}
                style={{ padding: '6px 16px', fontSize: 12, background: '#22c55e',
                  color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}>
                Save & Switch
              </button>
            </div>
          </div>
        </div>
      )}

      {/* New branch modal */}
      {showBranchModal === 'new-branch' && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 1000,
        }}>
          <div style={{
            background: 'var(--panel, #1e293b)', borderRadius: 8,
            padding: 24, maxWidth: 400, width: '90%',
            border: '1px solid var(--panel-border, #2d3748)',
          }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>
              Create New Branch
            </div>
            <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 8 }}>
              Fork from current state of &ldquo;{activeBranch?.name}&rdquo;
            </div>
            <input
              autoFocus
              type="text" placeholder="Branch name..."
              value={newBranchName}
              onChange={e => setNewBranchName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreateBranch()}
              style={{
                width: '100%', padding: '8px 12px', fontSize: 13, marginBottom: 12,
                background: 'var(--bg, #0f172a)',
                border: '1px solid var(--panel-border, #2d3748)',
                borderRadius: 4, color: 'var(--text, #e2e8f0)',
                boxSizing: 'border-box',
              }}
            />
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button onClick={() => { setShowBranchModal(false); setNewBranchName('') }}
                style={{ padding: '6px 16px', fontSize: 12, background: 'transparent',
                  border: '1px solid var(--panel-border, #2d3748)', borderRadius: 4,
                  color: 'var(--text, #e2e8f0)', cursor: 'pointer' }}>
                Cancel
              </button>
              <button onClick={handleCreateBranch}
                style={{ padding: '6px 16px', fontSize: 12, background: '#3b82f6',
                  color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}>
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main layout: sidebar + center */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 }}>
        <CommunityList
          communities={communities}
          selectedId={selectedCommunity?.id}
          onSelect={c => { setSelectedCommunity(c); setDeepDiveAccountId(null) }}
        />

        {deepDiveAccountId ? (
          /* Deep dive mode — full center panel */
          <AccountDeepDive
            accountId={deepDiveAccountId}
            egoAccountId={egoAccountId}
            allCommunities={communities}
            onBack={() => setDeepDiveAccountId(null)}
            onWeightsChanged={handleWeightsChanged}
          />
        ) : (
          /* List mode — community header + member table */
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0 }}>
            {/* Community edit bar */}
            {selectedCommunity && (
              <>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '6px 12px',
                  borderBottom: '1px solid var(--panel-border, #1e293b)',
                  background: 'var(--panel, #1e293b)',
                }}>
                  <input
                    type="color"
                    value={editingColor ?? selectedCommunity.color ?? '#64748b'}
                    onChange={e => setEditingColor(e.target.value)}
                    onBlur={() => {
                      if (editingColor && editingColor !== selectedCommunity.color) {
                        handleUpdateCommunity({ color: editingColor })
                      }
                      setEditingColor(null)
                    }}
                    style={{ width: 24, height: 24, border: 'none', padding: 0,
                      cursor: 'pointer', background: 'transparent' }}
                    title="Change color"
                  />
                  {editingName !== null ? (
                    <input
                      autoFocus value={editingName}
                      onChange={e => setEditingName(e.target.value)}
                      onBlur={() => {
                        if (editingName && editingName !== selectedCommunity.name) {
                          handleUpdateCommunity({ name: editingName })
                        } else { setEditingName(null) }
                      }}
                      onKeyDown={e => {
                        if (e.key === 'Enter') e.target.blur()
                        if (e.key === 'Escape') setEditingName(null)
                      }}
                      style={{
                        flex: 1, padding: '4px 8px', fontSize: 14, fontWeight: 600,
                        background: 'var(--bg, #0f172a)',
                        border: '1px solid var(--accent, #3b82f6)',
                        borderRadius: 4, color: 'var(--text, #e2e8f0)',
                      }}
                    />
                  ) : (
                    <span onClick={() => setEditingName(selectedCommunity.name)}
                      style={{ fontSize: 14, fontWeight: 600, cursor: 'pointer' }}
                      title="Click to rename">
                      {selectedCommunity.name}
                    </span>
                  )}
                  <span style={{ fontSize: 11, color: '#64748b' }}>
                    {selectedCommunity.member_count} members
                  </span>
                </div>
                <div style={{
                  padding: '4px 12px',
                  borderBottom: '1px solid var(--panel-border, #1e293b)',
                }}>
                  {editingDesc !== null ? (
                    <input
                      autoFocus value={editingDesc}
                      onChange={e => setEditingDesc(e.target.value)}
                      onBlur={() => {
                        if (editingDesc !== (selectedCommunity.description || '')) {
                          handleUpdateCommunity({ description: editingDesc || null })
                        }
                        setEditingDesc(null)
                      }}
                      onKeyDown={e => {
                        if (e.key === 'Enter') e.target.blur()
                        if (e.key === 'Escape') setEditingDesc(null)
                      }}
                      placeholder="Add a description..."
                      style={{
                        width: '100%', padding: '4px 8px', fontSize: 12,
                        background: 'var(--bg, #0f172a)',
                        border: '1px solid var(--accent, #3b82f6)',
                        borderRadius: 4, color: 'var(--text, #e2e8f0)',
                      }}
                    />
                  ) : (
                    <span
                      onClick={() => setEditingDesc(selectedCommunity.description || '')}
                      style={{
                        fontSize: 12, cursor: 'pointer',
                        color: selectedCommunity.description ? 'var(--text, #e2e8f0)' : '#475569',
                        fontStyle: selectedCommunity.description ? 'normal' : 'italic',
                      }}
                      title="Click to edit description">
                      {selectedCommunity.description || 'Add a description...'}
                    </span>
                  )}
                </div>
              </>
            )}

            {membersLoading ? (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center',
                justifyContent: 'center', color: '#64748b' }}>
                Loading members...
              </div>
            ) : (
              <MemberTable
                members={members}
                onSelectAccount={m => setDeepDiveAccountId(m.account_id)}
                showFollowOnly={showFollowOnly}
                onToggleFollowOnly={() => setShowFollowOnly(v => !v)}
                searchQuery={searchQuery}
                onSearchChange={setSearchQuery}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
