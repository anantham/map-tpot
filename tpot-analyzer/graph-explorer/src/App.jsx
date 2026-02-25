import { useState, useEffect, useCallback } from 'react'
import './App.css'
import GraphExplorer from './GraphExplorer'
import Discovery from './Discovery'
import ClusterView from './ClusterView'
import Labeling from './Labeling'
import Communities from './Communities'
import { getAccount, getTheme as loadTheme, setTheme as saveTheme } from './storage'

function App() {
  const getSavedAccount = () => getAccount()

  const getInitialView = () => {
    if (typeof window === 'undefined') return 'discovery'
    const params = new URLSearchParams(window.location.search)
    const view = params.get('view')
    if (view === 'cluster' || view === 'graph' || view === 'labeling' || view === 'communities') return view
    return 'discovery'
  }
  const [currentView, setCurrentView] = useState(getInitialView)
  const [accountStatus, setAccountStatus] = useState(getSavedAccount)

  useEffect(() => {
    setAccountStatus(getSavedAccount())
  }, [])

  const [theme, setTheme] = useState(() => loadTheme())

  useEffect(() => {
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', theme)
      saveTheme(theme)
    }
  }, [theme])

  const toggleTheme = useCallback(() => {
    setTheme(t => (t === 'dark' ? 'light' : 'dark'))
  }, [])

  const handleAccountStatusChange = useCallback(({ handle, valid }) => {
    setAccountStatus({
      handle: handle || '',
      valid: Boolean(handle) && Boolean(valid),
    })
  }, [])

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Navigation */}
      <div style={{
        display: 'flex',
        gap: '10px',
        padding: '10px 20px',
        background: 'var(--panel)',
        borderBottom: '1px solid var(--panel-border)',
        color: 'var(--text)'
      }}>
        <button
          onClick={() => setCurrentView('discovery')}
          style={{
            padding: '8px 16px',
            background: currentView === 'discovery' ? 'var(--accent)' : 'var(--panel)',
            color: currentView === 'discovery' ? 'var(--bg)' : 'var(--text)',
            border: '1px solid var(--panel-border)',
            borderRadius: '6px',
            cursor: 'pointer',
            fontWeight: '600'
          }}
        >
          Discovery
        </button>
        <button
          onClick={() => accountStatus.valid && setCurrentView('graph')}
          disabled={!accountStatus.valid}
          style={{
            padding: '8px 16px',
            background: currentView === 'graph' ? 'var(--accent)' : 'var(--panel)',
            color: currentView === 'graph' ? 'var(--bg)' : 'var(--text)',
            border: '1px solid var(--panel-border)',
            borderRadius: '6px',
            cursor: accountStatus.valid ? 'pointer' : 'not-allowed',
            fontWeight: '600'
          }}
        >
          Graph Explorer
        </button>
        <button
          onClick={() => setCurrentView('cluster')}
          style={{
            padding: '8px 16px',
            background: currentView === 'cluster' ? 'var(--accent)' : 'var(--panel)',
            color: currentView === 'cluster' ? 'var(--bg)' : 'var(--text)',
            border: '1px solid var(--panel-border)',
            borderRadius: '6px',
            cursor: 'pointer',
            fontWeight: '600'
          }}
        >
          Cluster View
        </button>
        <button
          onClick={() => setCurrentView('communities')}
          style={{
            padding: '8px 16px',
            background: currentView === 'communities' ? 'var(--accent)' : 'var(--panel)',
            color: currentView === 'communities' ? 'var(--bg)' : 'var(--text)',
            border: '1px solid var(--panel-border)',
            borderRadius: '6px',
            cursor: 'pointer',
            fontWeight: '600'
          }}
        >
          Communities
        </button>
        <button
          onClick={() => setCurrentView('labeling')}
          style={{
            padding: '8px 16px',
            background: currentView === 'labeling' ? '#3b82f6' : 'var(--panel)',
            color: currentView === 'labeling' ? '#fff' : 'var(--text)',
            border: '1px solid var(--panel-border)',
            borderRadius: '6px',
            cursor: 'pointer',
            fontWeight: '600'
          }}
        >
          Label Tweets
        </button>
        <div style={{ flex: 1 }} />
      </div>

      {/* Main Content - render both but hide inactive one */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {currentView === 'discovery' && (
          <div style={{ height: '100%' }}>
            <Discovery
              initialAccount={accountStatus.handle}
              onAccountStatusChange={handleAccountStatusChange}
            />
          </div>
        )}
        {currentView === 'graph' && (
          <div style={{ height: '100%' }}>
            {accountStatus.valid ? (
              <GraphExplorer dataUrl="/analysis_output.json" />
            ) : (
              <div style={{
                height: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexDirection: 'column',
                gap: '12px',
                color: '#475569',
                padding: '24px'
              }}>
                <h2 style={{ margin: 0 }}>Set “My Account” in Discovery first</h2>
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
            <ClusterView
              defaultEgo={accountStatus.handle}
              theme={theme}
              onThemeChange={toggleTheme}
            />
          </div>
        )}
        {currentView === 'communities' && (
          <div style={{ height: '100%' }}>
            <Communities ego={accountStatus.handle} />
          </div>
        )}
        {currentView === 'labeling' && (
          <div style={{ height: '100%' }}>
            <Labeling reviewer={accountStatus.handle || 'human'} />
          </div>
        )}
      </div>
    </div>
  )
}

export default App
