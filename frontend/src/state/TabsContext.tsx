import { createContext, useCallback, useContext, useMemo, useReducer, type ReactNode } from 'react'
import type { Host } from '../api/types'

export interface Tab {
  id: string
  hostId: number
  label: string
  aiPanelOpen: boolean
}

interface TabsState {
  tabs: Tab[]
  activeTabId: string | null
}

type Action =
  | { type: 'open'; tab: Tab }
  | { type: 'close'; tabId: string }
  | { type: 'activate'; tabId: string }
  | { type: 'toggleAgentPanel'; tabId: string }

function reducer(state: TabsState, action: Action): TabsState {
  switch (action.type) {
    case 'open':
      return { tabs: [...state.tabs, action.tab], activeTabId: action.tab.id }
    case 'close': {
      const tabs = state.tabs.filter((t) => t.id !== action.tabId)
      const wasActive = state.activeTabId === action.tabId
      const closedIndex = state.tabs.findIndex((t) => t.id === action.tabId)
      const activeTabId = wasActive
        ? (tabs[closedIndex] ?? tabs[closedIndex - 1] ?? tabs[0])?.id ?? null
        : state.activeTabId
      return { tabs, activeTabId }
    }
    case 'activate':
      return { ...state, activeTabId: action.tabId }
    case 'toggleAgentPanel':
      return {
        ...state,
        tabs: state.tabs.map((t) =>
          t.id === action.tabId ? { ...t, aiPanelOpen: !t.aiPanelOpen } : t,
        ),
      }
  }
}

interface TabsContextValue extends TabsState {
  openTab: (host: Host) => void
  closeTab: (tabId: string) => void
  activateTab: (tabId: string) => void
  toggleAgentPanel: (tabId: string) => void
}

const TabsContext = createContext<TabsContextValue | null>(null)

export function TabsProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, { tabs: [], activeTabId: null })

  const openTab = useCallback((host: Host) => {
    const tab: Tab = {
      id: typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `${host.id}-${Date.now()}`,
      hostId: host.id,
      label: host.label,
      aiPanelOpen: false,
    }
    dispatch({ type: 'open', tab })
  }, [])

  const closeTab = useCallback((tabId: string) => dispatch({ type: 'close', tabId }), [])
  const activateTab = useCallback((tabId: string) => dispatch({ type: 'activate', tabId }), [])
  const toggleAgentPanel = useCallback((tabId: string) => dispatch({ type: 'toggleAgentPanel', tabId }), [])

  const value = useMemo(
    () => ({ ...state, openTab, closeTab, activateTab, toggleAgentPanel }),
    [state, openTab, closeTab, activateTab, toggleAgentPanel],
  )

  return <TabsContext.Provider value={value}>{children}</TabsContext.Provider>
}

export function useTabs(): TabsContextValue {
  const ctx = useContext(TabsContext)
  if (!ctx) throw new Error('useTabs must be used within a TabsProvider')
  return ctx
}
