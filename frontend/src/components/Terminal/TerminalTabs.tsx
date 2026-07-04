import { useTabs } from '../../state/TabsContext'
import { AgentPanel } from '../Agent/AgentPanel'
import { TerminalPane } from './TerminalPane'

export function TerminalTabs() {
  const { tabs, activeTabId, closeTab, activateTab, toggleAgentPanel } = useTabs()

  if (tabs.length === 0) {
    return <div className="terminal-tabs-empty">Double-click a host in the sidebar to connect.</div>
  }

  return (
    <div className="terminal-tabs">
      <div className="tab-bar">
        {tabs.map((tab) => (
          <div
            key={tab.id}
            className={`tab ${tab.id === activeTabId ? 'tab--active' : ''}`}
            onClick={() => activateTab(tab.id)}
          >
            <span className="tab-label">{tab.label}</span>
            <button
              type="button"
              className="tab-close"
              onClick={(e) => {
                e.stopPropagation()
                closeTab(tab.id)
              }}
              aria-label={`Close ${tab.label}`}
            >
              ×
            </button>
          </div>
        ))}
      </div>
      <div className="tab-content">
        {tabs.map((tab) => (
          <div key={tab.id} className="tab-pane-slot" style={{ display: tab.id === activeTabId ? 'flex' : 'none' }}>
            <div className="terminal-with-agent">
              <TerminalPane
                hostId={tab.hostId}
                isActive={tab.id === activeTabId}
                sessionId={tab.id}
                aiPanelOpen={tab.aiPanelOpen}
                onToggleAgentPanel={() => toggleAgentPanel(tab.id)}
                onSessionEnded={() => closeTab(tab.id)}
              />
              {tab.aiPanelOpen && <AgentPanel sessionId={tab.id} />}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
