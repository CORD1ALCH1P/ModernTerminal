import { useEffect, useRef, useState } from 'react'
import { useTabs } from '../../state/TabsContext'
import { AgentPanel } from '../Agent/AgentPanel'
import { TerminalPane } from './TerminalPane'

const DEFAULT_AGENT_PANEL_WIDTH = 360
const MIN_AGENT_PANEL_WIDTH = 260
const MAX_AGENT_PANEL_WIDTH = 800

export function TerminalTabs() {
  const { tabs, activeTabId, closeTab, activateTab, toggleAgentPanel } = useTabs()
  const [agentPanelWidth, setAgentPanelWidth] = useState(DEFAULT_AGENT_PANEL_WIDTH)
  const resizingRef = useRef(false)

  // A single shared width (not per-tab) so resizing once applies consistently
  // everywhere, the same way most split-pane UIs (e.g. an editor's sidebar)
  // remember one width across tabs rather than a different one per tab.
  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!resizingRef.current) return
      const newWidth = window.innerWidth - e.clientX
      setAgentPanelWidth(Math.min(Math.max(newWidth, MIN_AGENT_PANEL_WIDTH), MAX_AGENT_PANEL_WIDTH))
    }
    const stopResizing = () => {
      if (!resizingRef.current) return
      resizingRef.current = false
      document.body.classList.remove('resizing-col')
    }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', stopResizing)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', stopResizing)
    }
  }, [])

  const startResizing = () => {
    resizingRef.current = true
    document.body.classList.add('resizing-col')
  }

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
                sessionId={tab.id}
                aiPanelOpen={tab.aiPanelOpen}
                onToggleAgentPanel={() => toggleAgentPanel(tab.id)}
                onSessionEnded={() => closeTab(tab.id)}
              />
              {tab.aiPanelOpen && (
                <>
                  <div className="agent-resize-handle" onMouseDown={startResizing} />
                  <div className="agent-panel-wrapper" style={{ width: agentPanelWidth }}>
                    <AgentPanel sessionId={tab.id} />
                  </div>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
