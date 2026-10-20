import { useState } from 'react'

import './AppNavigation.css'

const TOOL_DESTINATIONS = [
  { label: 'Discovery', view: 'discovery' },
  { label: 'Graph Explorer', view: 'graph', needsAccount: true },
  { label: 'Communities', view: 'communities' },
  { label: 'Label Tweets', view: 'labeling' },
]

export default function AppNavigation({
  accountValid = false,
  currentView,
  onNavigate,
}) {
  const [toolsOpen, setToolsOpen] = useState(false)
  const primaryView = currentView === 'research-notes'
    ? 'research-notes'
    : currentView === 'cluster'
      ? 'cluster'
      : null

  const navigate = (view) => {
    setToolsOpen(false)
    onNavigate(view)
  }

  return (
    <nav className="app-navigation" aria-label="Product navigation">
      <div className="app-navigation-primary">
        <button
          type="button"
          aria-current={primaryView === 'research-notes' ? 'page' : undefined}
          className={primaryView === 'research-notes' ? 'active' : ''}
          onClick={() => navigate('research-notes')}
        >
          Review
        </button>
        <button
          type="button"
          aria-current={primaryView === 'cluster' ? 'page' : undefined}
          className={primaryView === 'cluster' ? 'active' : ''}
          onClick={() => navigate('cluster')}
        >
          Map
        </button>
      </div>
      <div className="app-navigation-tools">
        <button
          type="button"
          aria-expanded={toolsOpen}
          aria-haspopup="menu"
          onClick={() => setToolsOpen((open) => !open)}
        >
          Tools
        </button>
        {toolsOpen && (
          <div className="app-navigation-menu" role="menu">
            {TOOL_DESTINATIONS.map((destination) => (
              <button
                type="button"
                role="menuitem"
                key={destination.view}
                disabled={destination.needsAccount && !accountValid}
                onClick={() => navigate(destination.view)}
              >
                {destination.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </nav>
  )
}
