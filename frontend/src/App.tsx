import './App.css'
import { SessionTree } from './components/SessionTree/SessionTree'
import { TerminalTabs } from './components/Terminal/TerminalTabs'
import { SessionTreeProvider } from './state/SessionTreeContext'
import { TabsProvider } from './state/TabsContext'

function App() {
  return (
    <SessionTreeProvider>
      <TabsProvider>
        <div className="app-layout">
          <aside className="app-sidebar">
            <SessionTree />
          </aside>
          <main className="app-main">
            <TerminalTabs />
          </main>
        </div>
      </TabsProvider>
    </SessionTreeProvider>
  )
}

export default App
