/**
 * Presentational sidebar for cluster details in ClusterView.
 *
 * Displays: cluster info, expand/collapse controls, rename form,
 * tag summary, member list, and account tagging panel.
 */

import AccountTagPanel from './AccountTagPanel'
import AccountMembershipPanel from './AccountMembershipPanel'

export default function ClusterDetailsSidebar({
  cluster,
  // Expand / Collapse
  expandPreview,
  collapsePreview,
  collapseSelected,
  onExpand,
  onCollapse,
  onToggleCollapseSelection,
  // Rename
  labelDraft,
  onLabelDraftChange,
  onRename,
  onDeleteLabel,
  // Tag summary
  ego,
  tagSummary,
  tagSummaryLoading,
  tagSummaryError,
  onApplySuggestedLabel,
  // Members
  members,
  membersTotal,
  onMemberSelect,
  // Account tagging
  selectedAccount,
  membership,
  membershipLoading,
  membershipError,
  onTagChanged,
}) {
  if (!cluster) return null

  return (
    // Outer chrome (positioning, close button, scroll container) is owned by
    // the Drawer wrapper in ClusterView. This component now renders body
    // content only — keeps it composable and lets the Drawer handle Escape
    // / pointer-events / animations uniformly across panels.
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ fontWeight: 700, fontSize: 15 }}>{cluster.label}</div>
      <div style={{ color: 'var(--text-muted, #475569)', fontSize: 13 }}>
        Size {cluster.size} • Reps {(cluster.representativeHandles || []).join(', ')}
      </div>

        {/* Community breakdown */}
        {cluster.communityBreakdown?.length > 0 && (
          <div style={{ marginTop: 4 }}>
            {/* Stacked bar */}
            <div style={{
              display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden',
              background: 'rgba(140,140,140,0.2)',
            }}>
              {cluster.communityBreakdown.slice(0, 6).map((seg, i) => (
                <div
                  key={i}
                  style={{
                    width: `${(seg.weight * 100).toFixed(1)}%`,
                    background: seg.color,
                    minWidth: seg.weight > 0.02 ? 3 : 0,
                  }}
                  title={`${seg.name}: ${(seg.weight * 100).toFixed(0)}%`}
                />
              ))}
            </div>
            {/* Top communities with dot + name + percentage */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '2px 10px', marginTop: 4, fontSize: 11 }}>
              {cluster.communityBreakdown.slice(0, 4).map((seg, i) => (
                <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 3, color: '#475569' }}>
                  <span style={{
                    display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
                    background: seg.color, flexShrink: 0,
                  }} />
                  {seg.name} {(seg.weight * 100).toFixed(0)}%
                </span>
              ))}
            </div>
          </div>
        )}

        <label style={{ display: 'flex', gap: 6, alignItems: 'center', color: '#475569' }}>
          <input
            type="checkbox"
            checked={collapseSelected}
            onChange={onToggleCollapseSelection}
          />
          Select for collapse
        </label>
        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          <button
            onClick={onExpand}
            disabled={!expandPreview?.can_expand || cluster.isLeaf}
            style={{ padding: '8px 12px', borderRadius: 6, background: '#0ea5e9', color: 'white', border: 'none', opacity: (!expandPreview?.can_expand || cluster.isLeaf) ? 0.6 : 1 }}
            title={expandPreview?.reason || ''}
          >
            Expand {expandPreview?.can_expand ? `(+${expandPreview.budget_impact} → ${expandPreview.predicted_children} clusters)` : (cluster.isLeaf ? '(leaf)' : '')}
          </button>
          <button
            onClick={onCollapse}
            disabled={!collapsePreview?.can_collapse}
            style={{ padding: '8px 12px', borderRadius: 6, background: '#334155', color: 'white', border: 'none', opacity: collapsePreview?.can_collapse ? 1 : 0.6 }}
            title={collapsePreview?.can_collapse ? `Merges ${collapsePreview.sibling_ids?.length || 0} clusters` : (collapsePreview?.reason || '')}
          >
            Collapse {collapsePreview?.can_collapse ? `(frees ${collapsePreview.nodes_freed})` : ''}
          </button>
        </div>
        <label style={{ fontWeight: 600, marginTop: 8 }}>Rename</label>
        <input
          value={labelDraft}
          onChange={e => onLabelDraftChange(e.target.value)}
          style={{ padding: '6px 8px', borderRadius: 6, border: '1px solid #cbd5e1' }}
        />
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={onRename} style={{ padding: '8px 12px', borderRadius: 6, background: '#1d4ed8', color: 'white', border: 'none' }}>
            Save
          </button>
          <button onClick={onDeleteLabel} style={{ padding: '8px 12px', borderRadius: 6, background: '#e11d48', color: 'white', border: 'none' }}>
            Delete
          </button>
        </div>
        {/* Tag summary — collapsed by default so the drawer opens lightweight */}
        <details style={{ marginTop: 8 }}>
          <summary style={{ fontWeight: 600, cursor: 'pointer', padding: '4px 0' }}>
            Tag summary{tagSummary?.tagCounts ? ` (${tagSummary.tagCounts.length})` : ''}
          </summary>
          <div style={{ marginTop: 8 }}>
            {!ego && (
              <div style={{ color: '#94a3b8' }}>Set `ego` in Settings to compute tag summary.</div>
            )}
            {ego && tagSummaryLoading && <div style={{ color: '#94a3b8' }}>Loading tag summary…</div>}
            {ego && tagSummaryError && <div style={{ color: '#b91c1c' }}>{tagSummaryError}</div>}
            {ego && !tagSummaryLoading && !tagSummaryError && tagSummary && (
              <div style={{ border: '1px solid #e2e8f0', borderRadius: 10, padding: 10, background: 'rgba(148,163,184,0.08)' }}>
                <div style={{ color: '#475569', fontSize: 13 }}>
                  Tagged members: {tagSummary.taggedMembers}/{tagSummary.totalMembers} • Assignments: {tagSummary.tagAssignments} • Compute: {tagSummary.computeMs}ms
                </div>
                {tagSummary.suggestedLabel?.tag && (
                  <div style={{ marginTop: 8 }}>
                    <div style={{ fontWeight: 700 }}>Suggested label</div>
                    <div style={{ color: '#475569', fontSize: 13 }}>
                      {tagSummary.suggestedLabel.tag} (score {tagSummary.suggestedLabel.score})
                    </div>
                    <button
                      onClick={onApplySuggestedLabel}
                      style={{ marginTop: 8, padding: '8px 12px', borderRadius: 8, background: '#16a34a', color: 'white', border: 'none' }}
                    >
                      Apply suggested label
                    </button>
                  </div>
                )}
                <div style={{ marginTop: 10, fontWeight: 700 }}>Top tags</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 160, overflow: 'auto', marginTop: 6 }}>
                  {(tagSummary.tagCounts || []).slice(0, 12).map((row) => (
                    <div
                      key={row.tag}
                      style={{ display: 'flex', justifyContent: 'space-between', gap: 10, border: '1px solid #e2e8f0', borderRadius: 8, padding: '6px 8px', background: 'white' }}
                    >
                      <div style={{ fontWeight: 700 }}>{row.tag}</div>
                      <div style={{ color: '#475569', fontSize: 12, whiteSpace: 'nowrap' }}>
                        IN {row.inCount} · NOT {row.notInCount} · score {row.score}
                      </div>
                    </div>
                  ))}
                  {(!tagSummary.tagCounts || tagSummary.tagCounts.length === 0) && (
                    <div style={{ color: '#94a3b8' }}>No tags found for members in this cluster.</div>
                  )}
                </div>
              </div>
            )}
          </div>
        </details>

        {/* Members — collapsed by default; total is shown in the summary */}
        <details style={{ marginTop: 8 }}>
          <summary style={{ fontWeight: 600, cursor: 'pointer', padding: '4px 0' }}>
            Members ({membersTotal})
          </summary>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 240, overflow: 'auto', marginTop: 8 }}>
            {members.map(m => (
              <div
                key={m.id}
                onClick={() => onMemberSelect({ accountId: m.id, parentId: cluster.id, username: m.username, displayName: m.displayName })}
                style={{ border: '1px solid #e2e8f0', borderRadius: 6, padding: 8, cursor: 'pointer' }}
                title="Select account to tag"
              >
                <div style={{ fontWeight: 600 }}>{m.username || m.id}</div>
                <div style={{ color: '#475569', fontSize: 13 }}>Followers: {m.numFollowers ?? '–'}</div>
              </div>
            ))}
            {!members.length && <div style={{ color: '#94a3b8' }}>No members loaded</div>}
          </div>
        </details>

        {/* Selected account — auto-opens when an account is selected so
            the tagging UI is visible without an extra click */}
        <details style={{ marginTop: 8 }} open={!!selectedAccount}>
          <summary style={{ fontWeight: 700, cursor: 'pointer', padding: '4px 0' }}>
            Selected account
          </summary>
          <div style={{ marginTop: 8 }}>
            {!selectedAccount && <div style={{ color: '#94a3b8' }}>Click a member to tag.</div>}
            {selectedAccount && (
              <>
                <div style={{ color: '#475569' }}>
                  @{selectedAccount.username || selectedAccount.id}{selectedAccount.displayName ? ` · ${selectedAccount.displayName}` : ''}
                </div>
                <AccountMembershipPanel
                  ego={ego}
                  account={selectedAccount}
                  loading={membershipLoading}
                  error={membershipError}
                  membership={membership}
                />
                <AccountTagPanel
                  ego={ego}
                  account={selectedAccount}
                  onTagChanged={onTagChanged}
                />
              </>
            )}
          </div>
        </details>
    </div>
  )
}
