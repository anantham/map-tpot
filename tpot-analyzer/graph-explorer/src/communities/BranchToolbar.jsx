import { useCallback, useState } from 'react'

function ModalShell({ title, children }) {
  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(0,0,0,0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
    }}>
      <div style={{
        background: 'var(--panel, #1e293b)',
        borderRadius: 8,
        padding: 24,
        maxWidth: 400,
        width: '90%',
        border: '1px solid var(--panel-border, #2d3748)',
      }}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>
          {title}
        </div>
        {children}
      </div>
    </div>
  )
}

export default function BranchToolbar({
  branches,
  activeBranch,
  isDirty,
  onSwitchBranch,
  onSaveSnapshot,
  onCreateBranch,
}) {
  const [modal, setModal] = useState(null)
  const [pendingSwitchId, setPendingSwitchId] = useState(null)
  const [newBranchName, setNewBranchName] = useState('')

  const closeModal = useCallback(() => {
    setModal(null)
    setPendingSwitchId(null)
    setNewBranchName('')
  }, [])

  const initiateSwitch = useCallback(async (branchId) => {
    if (!activeBranch || branchId === activeBranch.id) return
    if (isDirty) {
      setPendingSwitchId(branchId)
      setModal('switch-confirm')
      return
    }
    await onSwitchBranch(branchId, 'discard')
  }, [activeBranch, isDirty, onSwitchBranch])

  const handleCreateBranch = useCallback(async () => {
    if (!newBranchName.trim()) return
    await onCreateBranch(newBranchName.trim())
    closeModal()
  }, [closeModal, newBranchName, onCreateBranch])

  return (
    <>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '6px 16px',
        borderBottom: '1px solid var(--panel-border, #1e293b)',
        background: 'var(--panel, #1e293b)',
        fontSize: 12,
        flexShrink: 0,
      }}>
        <span style={{ color: '#64748b', fontWeight: 600 }}>Branch:</span>
        <select
          value={activeBranch?.id || ''}
          onChange={(event) => initiateSwitch(event.target.value)}
          disabled={branches.length === 0}
          style={{
            padding: '4px 8px',
            fontSize: 12,
            background: 'var(--bg, #0f172a)',
            border: '1px solid var(--panel-border, #2d3748)',
            borderRadius: 4,
            color: 'var(--text, #e2e8f0)',
          }}
        >
          {branches.map((branch) => (
            <option key={branch.id} value={branch.id}>
              {branch.name} ({branch.snapshot_count} saves)
            </option>
          ))}
        </select>
        <button
          onClick={onSaveSnapshot}
          disabled={!activeBranch}
          style={{
            padding: '4px 10px',
            fontSize: 12,
            fontWeight: 600,
            background: '#22c55e',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            cursor: activeBranch ? 'pointer' : 'not-allowed',
          }}
        >
          Save
        </button>
        <button
          onClick={() => setModal('new-branch')}
          style={{
            padding: '4px 10px',
            fontSize: 12,
            fontWeight: 600,
            background: '#3b82f6',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer',
          }}
        >
          Branch...
        </button>
        {isDirty && (
          <span style={{ color: '#f59e0b', fontWeight: 600 }}>
            unsaved changes
          </span>
        )}
      </div>

      {modal === 'switch-confirm' && (
        <ModalShell title={`Unsaved changes on "${activeBranch?.name}"`}>
          <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 16 }}>
            Save your changes before switching, or discard them?
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button
              onClick={closeModal}
              style={{
                padding: '6px 16px',
                fontSize: 12,
                background: 'transparent',
                border: '1px solid var(--panel-border, #2d3748)',
                borderRadius: 4,
                color: 'var(--text, #e2e8f0)',
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              onClick={async () => {
                await onSwitchBranch(pendingSwitchId, 'discard')
                closeModal()
              }}
              style={{
                padding: '6px 16px',
                fontSize: 12,
                background: '#ef4444',
                color: '#fff',
                border: 'none',
                borderRadius: 4,
                cursor: 'pointer',
              }}
            >
              Discard
            </button>
            <button
              onClick={async () => {
                await onSwitchBranch(pendingSwitchId, 'save')
                closeModal()
              }}
              style={{
                padding: '6px 16px',
                fontSize: 12,
                background: '#22c55e',
                color: '#fff',
                border: 'none',
                borderRadius: 4,
                cursor: 'pointer',
              }}
            >
              Save & Switch
            </button>
          </div>
        </ModalShell>
      )}

      {modal === 'new-branch' && (
        <ModalShell title="Create New Branch">
          <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 8 }}>
            Fork from current state of "{activeBranch?.name}"
          </div>
          <input
            autoFocus
            type="text"
            placeholder="Branch name..."
            value={newBranchName}
            onChange={(event) => setNewBranchName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') handleCreateBranch()
            }}
            style={{
              width: '100%',
              padding: '8px 12px',
              fontSize: 13,
              marginBottom: 12,
              background: 'var(--bg, #0f172a)',
              border: '1px solid var(--panel-border, #2d3748)',
              borderRadius: 4,
              color: 'var(--text, #e2e8f0)',
              boxSizing: 'border-box',
            }}
          />
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button
              onClick={closeModal}
              style={{
                padding: '6px 16px',
                fontSize: 12,
                background: 'transparent',
                border: '1px solid var(--panel-border, #2d3748)',
                borderRadius: 4,
                color: 'var(--text, #e2e8f0)',
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              onClick={handleCreateBranch}
              style={{
                padding: '6px 16px',
                fontSize: 12,
                background: '#3b82f6',
                color: '#fff',
                border: 'none',
                borderRadius: 4,
                cursor: 'pointer',
              }}
            >
              Create
            </button>
          </div>
        </ModalShell>
      )}
    </>
  )
}
