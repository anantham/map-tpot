import { useState, useEffect, useCallback } from 'react'
import './App.css'
import GraphExplorer from './GraphExplorer'
import Discovery from './Discovery'

function App() {
  const getSavedAccount = () => {
    if (typeof window === 'undefined') {
      return { handle: '', valid: false }
    }
    const handle = localStorage.getItem('discovery_my_account') || ''
    const valid = localStorage.getItem('discovery_my_account_valid') === 'true'
    return { handle, valid: Boolean(handle) && valid }
  }

  const [currentView, setCurrentView] = useState('discovery')
  const [preloadGraph, setPreloadGraph] = useState(false)
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

  // Preload Graph Explorer in background immediately
  useEffect(() => {
    console.log('[APP] Starting background preload of Graph Explorer')
    setPreloadGraph(true)
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
      </div>

      {/* Main Content - render both but hide inactive one */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        <div style={{ display: currentView === 'discovery' ? 'block' : 'none', height: '100%' }}>
          <Discovery
            initialAccount={accountStatus.handle}
            onAccountStatusChange={handleAccountStatusChange}
          />
        </div>
        {preloadGraph && (
          <div style={{ display: currentView === 'graph' ? 'block' : 'none', height: '100%' }}>
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
      </div>
    </div>
  )
}

export default App
