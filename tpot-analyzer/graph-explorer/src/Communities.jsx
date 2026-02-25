/**
 * Communities — Account community curation dashboard.
 *
 * Flow:
 *   1. Load communities list from /api/communities
 *   2. Click community → load members with I-follow badges
 *   3. Click member → see community distribution + bio + actions
 *   4. Assign/remove/move accounts → persists as source='human'
 */
import { useState, useEffect, useCallback } from 'react'
import { API_BASE_URL } from './config'
import {
  fetchCommunities,
  fetchCommunityMembers,
  fetchAccountCommunities,
  assignMember,
  removeMember,
  updateCommunity,
} from './communitiesApi'


function CommunityList({ communities, selectedId, onSelect }) {
  return (
    <div style={{
      width: 240, borderRight: '1px solid var(--panel-border, #1e293b)',
      overflowY: 'auto', padding: '12px 0',
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


function MemberTable({ members, selectedAccountId, onSelectAccount, showFollowOnly,
  onToggleFollowOnly, searchQuery, onSearchChange }) {
  const filtered = members.filter(m => {
    if (showFollowOnly && !m.i_follow) return false
    if (searchQuery && !m.username?.toLowerCase().includes(searchQuery.toLowerCase())) return false
    return true
  })

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      {/* Filters */}
      <div style={{
        display: 'flex', gap: 8, padding: '8px 12px', alignItems: 'center',
        borderBottom: '1px solid var(--panel-border, #1e293b)',
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

      {/* Table */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
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
                  background: selectedAccountId === m.account_id
                    ? 'var(--accent-dim, rgba(59,130,246,0.1))' : 'transparent',
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
                      maxWidth: 300 }}>
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


function AccountDetail({ account, accountCommunities, communities, currentCommunityId,
  onAssign, onRemove, assigning }) {
  const [moveTarget, setMoveTarget] = useState('')

  if (!account) return (
    <div style={{
      width: 300, borderLeft: '1px solid var(--panel-border, #1e293b)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      color: '#475569', fontSize: 13, padding: 24, textAlign: 'center',
    }}>
      Click an account to see details
    </div>
  )

  const otherCommunities = communities.filter(c => c.id !== currentCommunityId)

  return (
    <div style={{
      width: 300, borderLeft: '1px solid var(--panel-border, #1e293b)',
      overflowY: 'auto', padding: 16,
    }}>
      {/* Header */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 16, fontWeight: 700 }}>
          @{account.username || account.account_id}
        </div>
        {account.bio && (
          <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4, lineHeight: 1.5 }}>
            {account.bio}
          </div>
        )}
        {account.username && (
          <a
            href={`https://x.com/${account.username}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontSize: 12, color: '#3b82f6', marginTop: 6, display: 'inline-block' }}
          >
            Open on X →
          </a>
        )}
      </div>

      {/* Community memberships */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b',
          textTransform: 'uppercase', marginBottom: 8 }}>
          Communities
        </div>
        {accountCommunities.map(c => (
          <div key={c.community_id} style={{
            display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6,
          }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%',
              background: c.color || '#64748b', flexShrink: 0,
            }} />
            <span style={{ flex: 1, fontSize: 13 }}>{c.name}</span>
            <div style={{
              width: 60, height: 6, background: 'rgba(148,163,184,0.2)',
              borderRadius: 3, overflow: 'hidden',
            }}>
              <div style={{
                width: `${(c.weight * 100)}%`, height: '100%',
                background: c.color || '#3b82f6', borderRadius: 3,
              }} />
            </div>
            <span style={{ fontSize: 11, color: '#94a3b8', width: 32, textAlign: 'right',
              fontVariantNumeric: 'tabular-nums' }}>
              {(c.weight * 100).toFixed(0)}%
            </span>
          </div>
        ))}
        {accountCommunities.length === 0 && (
          <div style={{ fontSize: 12, color: '#475569' }}>Not in any community</div>
        )}
      </div>

      {/* Actions */}
      <div style={{
        background: 'var(--panel, #1e293b)',
        border: '1px solid var(--panel-border, #2d3748)',
        borderRadius: 8, padding: 12,
      }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b',
          textTransform: 'uppercase', marginBottom: 8 }}>
          Actions
        </div>

        {/* Assign to community */}
        <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
          <select
            value={moveTarget}
            onChange={e => setMoveTarget(e.target.value)}
            style={{
              flex: 1, padding: '6px 8px', fontSize: 12,
              background: 'var(--bg, #0f172a)',
              border: '1px solid var(--panel-border, #2d3748)',
              borderRadius: 4, color: 'var(--text, #e2e8f0)',
            }}
          >
            <option value="">Assign to...</option>
            {otherCommunities.map(c => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <button
            onClick={() => { if (moveTarget) { onAssign(moveTarget, account.account_id); setMoveTarget('') } }}
            disabled={!moveTarget || assigning}
            style={{
              padding: '6px 12px', fontSize: 12, fontWeight: 600,
              background: moveTarget ? '#3b82f6' : '#334155',
              color: '#fff', border: 'none', borderRadius: 4,
              cursor: moveTarget ? 'pointer' : 'not-allowed',
            }}
          >
            {assigning ? '...' : 'Add'}
          </button>
        </div>

        {/* Remove from current */}
        {currentCommunityId && (
          <button
            onClick={() => onRemove(currentCommunityId, account.account_id)}
            disabled={assigning}
            style={{
              width: '100%', padding: '6px 0', fontSize: 12, fontWeight: 600,
              background: 'transparent', color: '#f87171',
              border: '1px solid rgba(248,113,113,0.3)', borderRadius: 4,
              cursor: 'pointer',
            }}
          >
            Remove from this community
          </button>
        )}
      </div>
    </div>
  )
}


export default function Communities({ ego: defaultEgo }) {
  // Data state
  const [communities, setCommunities] = useState([])
  const [selectedCommunity, setSelectedCommunity] = useState(null)
  const [members, setMembers] = useState([])
  const [selectedAccount, setSelectedAccount] = useState(null)
  const [accountCommunities, setAccountCommunities] = useState([])

  // UI state
  const [loading, setLoading] = useState(true)
  const [membersLoading, setMembersLoading] = useState(false)
  const [error, setError] = useState(null)
  const [showFollowOnly, setShowFollowOnly] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [assigning, setAssigning] = useState(false)

  // Ego state — changeable
  const [ego, setEgo] = useState(defaultEgo || '')
  const [egoInput, setEgoInput] = useState(defaultEgo || '')
  const [egoAccountId, setEgoAccountId] = useState(null)

  // Resolve ego handle to account_id on change
  useEffect(() => {
    if (!ego) { setEgoAccountId(null); return }
    fetch(`${API_BASE_URL}/api/accounts/search?q=${encodeURIComponent(ego)}&limit=1`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        const match = data?.results?.[0]
        if (match && match.username?.toLowerCase() === ego.toLowerCase()) {
          setEgoAccountId(match.account_id)
        } else {
          setEgoAccountId(null)
        }
      })
      .catch(() => setEgoAccountId(null))
  }, [ego])

  // Load communities on mount
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

  // Load members when selected community or ego changes
  useEffect(() => {
    if (!selectedCommunity) return
    setMembersLoading(true)
    setSelectedAccount(null)
    setAccountCommunities([])
    setSearchQuery('')
    fetchCommunityMembers(selectedCommunity.id, { ego: egoAccountId })
      .then(data => setMembers(data.members || []))
      .catch(e => setError(e.message))
      .finally(() => setMembersLoading(false))
  }, [selectedCommunity?.id, egoAccountId])

  // Load account communities when account selected
  useEffect(() => {
    if (!selectedAccount) return
    fetchAccountCommunities(selectedAccount.account_id)
      .then(data => setAccountCommunities(data.communities || []))
      .catch(() => setAccountCommunities([]))
  }, [selectedAccount?.account_id])

  const refreshAfterEdit = useCallback(async (accountId) => {
    // Refresh member list
    if (selectedCommunity) {
      const data = await fetchCommunityMembers(selectedCommunity.id, { ego: egoAccountId })
      setMembers(data.members || [])
    }
    // Refresh account communities if same account
    if (accountId) {
      const acData = await fetchAccountCommunities(accountId)
      setAccountCommunities(acData.communities || [])
    }
    // Refresh community counts
    const comms = await fetchCommunities()
    setCommunities(comms)
  }, [selectedCommunity, egoAccountId])

  const handleAssign = useCallback(async (communityId, accountId) => {
    setAssigning(true)
    try {
      await assignMember(communityId, accountId)
      await refreshAfterEdit(accountId)
    } catch (e) {
      setError(e.message)
    } finally {
      setAssigning(false)
    }
  }, [refreshAfterEdit])

  const handleRemove = useCallback(async (communityId, accountId) => {
    setAssigning(true)
    try {
      await removeMember(communityId, accountId)
      setSelectedAccount(null)
      setAccountCommunities([])
      await refreshAfterEdit(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setAssigning(false)
    }
  }, [refreshAfterEdit])

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

      {/* Main 3-panel layout */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <CommunityList
          communities={communities}
          selectedId={selectedCommunity?.id}
          onSelect={setSelectedCommunity}
        />

        {membersLoading ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center',
            justifyContent: 'center', color: '#64748b' }}>
            Loading members...
          </div>
        ) : (
          <MemberTable
            members={members}
            selectedAccountId={selectedAccount?.account_id}
            onSelectAccount={setSelectedAccount}
            showFollowOnly={showFollowOnly}
            onToggleFollowOnly={() => setShowFollowOnly(v => !v)}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
          />
        )}

        <AccountDetail
          account={selectedAccount}
          accountCommunities={accountCommunities}
          communities={communities}
          currentCommunityId={selectedCommunity?.id}
          onAssign={handleAssign}
          onRemove={handleRemove}
          assigning={assigning}
        />
      </div>
    </div>
  )
}
