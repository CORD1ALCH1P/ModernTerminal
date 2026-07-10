import { useEffect, useRef, useState } from 'react'
import './App.css'
import { SessionTree } from './components/SessionTree/SessionTree'
import { TerminalTabs } from './components/Terminal/TerminalTabs'
import { SessionTreeProvider } from './state/SessionTreeContext'
import { TabsProvider } from './state/TabsContext'

const DEFAULT_SIDEBAR_WIDTH = 280
const MIN_SIDEBAR_WIDTH = 180
const MAX_SIDEBAR_WIDTH = 600

function App() {
  const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_SIDEBAR_WIDTH)
  const resizingRef = useRef(false)

  // Same drag pattern as the AI panel's resize handle (see TerminalTabs) --
  // window-level listeners so a fast drag that briefly leaves the thin handle
  // doesn't drop the resize.
  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!resizingRef.current) return
      setSidebarWidth(Math.min(Math.max(e.clientX, MIN_SIDEBAR_WIDTH), MAX_SIDEBAR_WIDTH))
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

  return (
    <SessionTreeProvider>
      <TabsProvider>
        <div className="app-layout">
          <aside className="app-sidebar" style={{ width: sidebarWidth }}>
            <SessionTree />
          </aside>
          <div className="sidebar-resize-handle" onMouseDown={startResizing} />
          <main className="app-main">
            <TerminalTabs />
          </main>
        </div>
      </TabsProvider>
    </SessionTreeProvider>
  )
}

export default App
