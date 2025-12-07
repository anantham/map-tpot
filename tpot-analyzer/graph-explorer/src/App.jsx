import { useState, useEffect, useCallback, useRef } from 'react'
import './App.css'
import GraphExplorer from './GraphExplorer'
import Discovery from './Discovery'
import ClusterView from './ClusterView'

function App() {
  const getSavedAccount = () => {
    if (typeof window === 'undefined') {
      return { handle: '', valid: false }
    }
    const handle = localStorage.getItem('discovery_my_account') || ''
    const valid = localStorage.getItem('discovery_my_account_valid') === 'true'
    return { handle, valid: Boolean(handle) && valid }
  }

  const getInitialView = () => {
    if (typeof window === 'undefined') return 'discovery'
    const params = new URLSearchParams(window.location.search)
    const view = params.get('view')
    if (view === 'cluster' || view === 'graph') return view
    return 'discovery'
  }
  const [currentView, setCurrentView] = useState(getInitialView)
  const [accountStatus, setAccountStatus] = useState(getSavedAccount)

  useEffect(() => {
    setAccountStatus(getSavedAccount())
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
        background: '#f7f9fa',
        borderBottom: '1px solid #e1e8ed'
      }}>
        <button
          onClick={() => setCurrentView('discovery')}
          style={{
            padding: '8px 16px',
            background: currentView === 'discovery' ? '#1da1f2' : 'white',
            color: currentView === 'discovery' ? 'white' : '#14171a',
            border: '1px solid #e1e8ed',
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
            background: currentView === 'graph' ? '#1da1f2' : 'white',
            color: currentView === 'graph' ? 'white' : '#14171a',
            border: '1px solid #e1e8ed',
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
            background: currentView === 'cluster' ? '#1da1f2' : 'white',
            color: currentView === 'cluster' ? 'white' : '#14171a',
            border: '1px solid #e1e8ed',
            borderRadius: '6px',
            cursor: 'pointer',
            fontWeight: '600'
          }}
        >
          Cluster View
        </button>
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
            <ClusterView defaultEgo={accountStatus.handle} />
          </div>
        )}
      </div>
    </div>
  )
}

export default App
