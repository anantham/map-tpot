import { useState } from 'react'
import './App.css'
import GraphExplorer from './GraphExplorer'
import Discovery from './Discovery'

function App() {
  const [currentView, setCurrentView] = useState('discovery')

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
          onClick={() => setCurrentView('graph')}
          style={{
            padding: '8px 16px',
            background: currentView === 'graph' ? '#1da1f2' : 'white',
            color: currentView === 'graph' ? 'white' : '#14171a',
            border: '1px solid #e1e8ed',
            borderRadius: '6px',
            cursor: 'pointer',
            fontWeight: '600'
          }}
        >
          Graph Explorer
        </button>
      </div>

      {/* Main Content */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {currentView === 'discovery' ? (
          <Discovery />
        ) : (
          <GraphExplorer dataUrl="/analysis_output.json" />
        )}
      </div>
    </div>
  )
}

export default App
