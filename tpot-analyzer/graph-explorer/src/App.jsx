import { useState, useEffect, useCallback } from 'react'
import './App.css'
import GraphExplorer from './GraphExplorer'
import Discovery from './Discovery'
import ClusterView from './ClusterView'
import Labeling from './Labeling'
import Communities from './Communities'
import { getAccount, getTheme as loadTheme, setTheme as saveTheme } from './storage'

const VALID_VIEWS = ['discovery', 'graph', 'labeling', 'communities', 'cluster']

function getInitialView() {
  if (typeof window === 'undefined') return 'discovery'
  const params = new URLSearchParams(window.location.search)
  const view = params.get('view')
  return VALID_VIEWS.includes(view) ? view : 'discovery'
}

function getInitialAccountId() {
  if (typeof window === 'undefined') return null
  return new URLSearchParams(window.location.search).get('accountId') || null
}

function App() {
  const [currentView, setCurrentView] = useState(getInitialView)
  const [accountStatus, setAccountStatus] = useState(() => getAccount())
  const [deepDiveAccountId, setDeepDiveAccountId] = useState(getInitialAccountId)

  useEffect(() => { setAccountStatus(getAccount()) }, [])

  // Sync URL whenever view or deepDiveAccountId changes
  useEffect(() => {
    const params = new URLSearchParams()
    params.set('view', currentView)
    if (deepDiveAccountId) params.set('accountId', deepDiveAccountId)
    history.replaceState(null, '', `?${params}`)
  }, [currentView, deepDiveAccountId])

  const [theme, setTheme] = useState(() => loadTheme())
  useEffect(() => {
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', theme)
      saveTheme(theme)
    }
  }, [theme])

  const toggleTheme = useCallback(() => setTheme(t => t === 'dark' ? 'light' : 'dark'), [])

  const handleAccountStatusChange = useCallback(({ handle, valid }) => {
    setAccountStatus({ handle: handle || '', valid: Boolean(handle) && Boolean(valid) })
  }, [])

  // Called from Labeling to jump to another view (optionally with state)
  const handleNavigate = useCallback((view, { accountId } = {}) => {
    if (accountId) setDeepDiveAccountId(accountId)
    setCurrentView(view)
  }, [])

  const nav = (view) => ({ onClick: () => { setCurrentView(view); setDeepDiveAccountId(null) } })
  const navStyle = (view) => ({
    padding: '8px 16px',
    background: currentView === view ? 'var(--accent)' : 'var(--panel)',
    color: currentView === view ? 'var(--bg)' : 'var(--text)',
    border: '1px solid var(--panel-border)',
    borderRadius: '6px',
    cursor: 'pointer',
    fontWeight: '600',
  })

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Navigation */}
      <div style={{
        display: 'flex', gap: '10px', padding: '10px 20px',
        background: 'var(--panel)', borderBottom: '1px solid var(--panel-border)', color: 'var(--text)',
      }}>
        <button {...nav('discovery')} style={navStyle('discovery')}>Discovery</button>
        <button
          onClick={() => accountStatus.valid && (setCurrentView('graph'), setDeepDiveAccountId(null))}
          disabled={!accountStatus.valid}
          style={{ ...navStyle('graph'), cursor: accountStatus.valid ? 'pointer' : 'not-allowed' }}
        >
          Graph Explorer
        </button>
        <button {...nav('cluster')} style={navStyle('cluster')}>Cluster View</button>
        <button {...nav('communities')} style={navStyle('communities')}>Communities</button>
        <button
          {...nav('labeling')}
          style={{
            ...navStyle('labeling'),
            background: currentView === 'labeling' ? '#3b82f6' : 'var(--panel)',
            color: currentView === 'labeling' ? '#fff' : 'var(--text)',
          }}
        >
          Label Tweets
        </button>
        <div style={{ flex: 1 }} />
      </div>

      {/* Main content */}
      <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        {currentView === 'discovery' && (
          <div style={{ height: '100%' }}>
            <Discovery initialAccount={accountStatus.handle} onAccountStatusChange={handleAccountStatusChange} />
          </div>
        )}
        {currentView === 'graph' && (
          <div style={{ height: '100%' }}>
            {accountStatus.valid ? (
              <GraphExplorer dataUrl="/analysis_output.json" />
            ) : (
              <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: '12px', color: '#475569', padding: '24px' }}>
                <h2 style={{ margin: 0 }}>Set "My Account" in Discovery first</h2>
                <p style={{ margin: 0, maxWidth: 480, textAlign: 'center' }}>
                  Graph Explorer needs your ego account to center the visualization.
                  Please enter and validate your handle in the Discovery tab.
                </p>
              </div>
            )}
          </div>
        )}
        {currentView === 'cluster' && (
          <div style={{ height: '100%' }}>
            <ClusterView defaultEgo={accountStatus.handle} theme={theme} onThemeChange={toggleTheme} />
          </div>
        )}
        {currentView === 'communities' && (
          <div style={{ height: '100%', overflow: 'hidden' }}>
            <Communities ego={accountStatus.handle} initialAccountId={deepDiveAccountId} />
          </div>
        )}
        {currentView === 'labeling' && (
          <div style={{ height: '100%' }}>
            <Labeling reviewer={accountStatus.handle || 'human'} onNavigate={handleNavigate} />
          </div>
        )}
      </div>
    </div>
  )
}

export default App
