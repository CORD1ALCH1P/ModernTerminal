import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from '../api/client'
import type {
  Folder,
  FolderCreateInput,
  FolderMoveInput,
  FolderRenameInput,
  Host,
  HostCreateInput,
  HostMoveInput,
  HostUpdateInput,
} from '../api/types'

interface SessionTreeState {
  folders: Folder[]
  hosts: Host[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  createFolder: (input: FolderCreateInput) => Promise<Folder>
  renameFolder: (id: number, input: FolderRenameInput) => Promise<void>
  moveFolder: (id: number, input: FolderMoveInput) => Promise<void>
  deleteFolder: (id: number) => Promise<void>
  createHost: (input: HostCreateInput) => Promise<Host>
  updateHost: (id: number, input: HostUpdateInput) => Promise<void>
  moveHost: (id: number, input: HostMoveInput) => Promise<void>
  deleteHost: (id: number) => Promise<void>
  acceptHostKey: (id: number, fingerprint: string) => Promise<void>
}

const SessionTreeContext = createContext<SessionTreeState | null>(null)

// Every mutation just re-fetches both lists rather than patching local state
// in place: folder moves can trigger server-side sibling sort_order
// renumbering (see backend crud.sort_order_for_index), and folder deletes
// cascade to descendants -- re-deriving from the server is simpler and safer
// than trying to keep a hand-rolled local mirror consistent with both, and
// the dataset size (tens/hundreds of rows) makes the extra round trip a
// non-issue.
export function SessionTreeProvider({ children }: { children: ReactNode }) {
  const [folders, setFolders] = useState<Folder[]>([])
  const [hosts, setHosts] = useState<Host[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const [folderList, hostList] = await Promise.all([api.listFolders(), api.listHosts()])
      setFolders(folderList)
      setHosts(hostList)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const createFolder = useCallback(
    async (input: FolderCreateInput) => {
      const folder = await api.createFolder(input)
      await refresh()
      return folder
    },
    [refresh],
  )

  const renameFolder = useCallback(
    async (id: number, input: FolderRenameInput) => {
      await api.renameFolder(id, input)
      await refresh()
    },
    [refresh],
  )

  const moveFolder = useCallback(
    async (id: number, input: FolderMoveInput) => {
      await api.moveFolder(id, input)
      await refresh()
    },
    [refresh],
  )

  const deleteFolder = useCallback(
    async (id: number) => {
      await api.deleteFolder(id)
      await refresh()
    },
    [refresh],
  )

  const createHost = useCallback(
    async (input: HostCreateInput) => {
      const host = await api.createHost(input)
      await refresh()
      return host
    },
    [refresh],
  )

  const updateHost = useCallback(
    async (id: number, input: HostUpdateInput) => {
      await api.updateHost(id, input)
      await refresh()
    },
    [refresh],
  )

  const moveHost = useCallback(
    async (id: number, input: HostMoveInput) => {
      await api.moveHost(id, input)
      await refresh()
    },
    [refresh],
  )

  const deleteHost = useCallback(
    async (id: number) => {
      await api.deleteHost(id)
      await refresh()
    },
    [refresh],
  )

  const acceptHostKey = useCallback(
    async (id: number, fingerprint: string) => {
      await api.acceptHostKey(id, fingerprint)
      await refresh()
    },
    [refresh],
  )

  const value = useMemo(
    () => ({
      folders,
      hosts,
      loading,
      error,
      refresh,
      createFolder,
      renameFolder,
      moveFolder,
      deleteFolder,
      createHost,
      updateHost,
      moveHost,
      deleteHost,
      acceptHostKey,
    }),
    [
      folders,
      hosts,
      loading,
      error,
      refresh,
      createFolder,
      renameFolder,
      moveFolder,
      deleteFolder,
      createHost,
      updateHost,
      moveHost,
      deleteHost,
      acceptHostKey,
    ],
  )

  return <SessionTreeContext.Provider value={value}>{children}</SessionTreeContext.Provider>
}

export function useSessionTree(): SessionTreeState {
  const ctx = useContext(SessionTreeContext)
  if (!ctx) throw new Error('useSessionTree must be used within a SessionTreeProvider')
  return ctx
}
