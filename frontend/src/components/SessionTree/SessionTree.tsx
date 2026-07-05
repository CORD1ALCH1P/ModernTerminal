import { useMemo, useState, type MouseEvent } from 'react'
import type { Folder, Host, HostCreateInput, HostUpdateInput } from '../../api/types'
import { AISettingsDialog } from '../Agent/AISettingsDialog'
import { FolderFormDialog } from '../HostDialog/FolderFormDialog'
import { HostFormDialog } from '../HostDialog/HostFormDialog'
import { useSessionTree } from '../../state/SessionTreeContext'
import { useTabs } from '../../state/TabsContext'
import { buildTree } from '../../state/buildTree'
import { FolderNode } from './FolderNode'
import { HostNode } from './HostNode'
import { TreeContextMenu, type MenuItem } from './TreeContextMenu'
import { APPEND_INDEX, makeDropTarget } from './useDragAndDrop'

interface ContextMenuState {
  x: number
  y: number
  items: MenuItem[]
}

interface FolderDialogState {
  mode: 'create' | 'rename'
  parentId: number | null
  folder?: Folder
}

interface HostDialogState {
  parentId: number | null
  host?: Host
}

export function SessionTree() {
  const {
    folders,
    hosts,
    loading,
    error,
    createFolder,
    renameFolder,
    moveFolder,
    deleteFolder,
    createHost,
    updateHost,
    moveHost,
    deleteHost,
  } = useSessionTree()
  const { openTab } = useTabs()

  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null)
  const [folderDialog, setFolderDialog] = useState<FolderDialogState | null>(null)
  const [hostDialog, setHostDialog] = useState<HostDialogState | null>(null)
  const [aiSettingsOpen, setAiSettingsOpen] = useState(false)

  const { roots, rootHosts } = useMemo(() => buildTree(folders, hosts), [folders, hosts])

  const openFolderContextMenu = (e: MouseEvent, folder: Folder) => {
    e.preventDefault()
    e.stopPropagation()
    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      items: [
        { label: 'New Subfolder', onClick: () => setFolderDialog({ mode: 'create', parentId: folder.id }) },
        { label: 'New Host', onClick: () => setHostDialog({ parentId: folder.id }) },
        {
          label: 'Rename',
          onClick: () => setFolderDialog({ mode: 'rename', parentId: folder.parent_id, folder }),
        },
        {
          label: 'Delete',
          danger: true,
          onClick: () => {
            if (confirm(`Delete folder "${folder.name}" and everything inside it?`)) {
              void deleteFolder(folder.id)
            }
          },
        },
      ],
    })
  }

  const openHostContextMenu = (e: MouseEvent, host: Host) => {
    e.preventDefault()
    e.stopPropagation()
    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      items: [
        { label: 'Connect', onClick: () => openTab(host) },
        { label: 'Edit', onClick: () => setHostDialog({ parentId: host.folder_id, host }) },
        {
          label: 'Delete',
          danger: true,
          onClick: () => {
            if (confirm(`Delete host "${host.label}"?`)) void deleteHost(host.id)
          },
        },
      ],
    })
  }

  const openRootContextMenu = (e: MouseEvent) => {
    e.preventDefault()
    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      items: [
        { label: 'New Folder', onClick: () => setFolderDialog({ mode: 'create', parentId: null }) },
        { label: 'New Host', onClick: () => setHostDialog({ parentId: null }) },
      ],
    })
  }

  const rootDrop = makeDropTarget(async (payload) => {
    try {
      if (payload.type === 'folder') {
        await moveFolder(payload.id, { parent_id: null, index: APPEND_INDEX })
      } else {
        await moveHost(payload.id, { folder_id: null, index: APPEND_INDEX })
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err))
    }
  })

  if (loading) return <div className="session-tree-loading">Loading…</div>

  return (
    <div className="session-tree" onContextMenu={openRootContextMenu} {...rootDrop}>
      <div className="session-tree-header">
        <span>Sessions</span>
        <button type="button" className="ai-settings-button" onClick={() => setAiSettingsOpen(true)}>
          AI Settings
        </button>
      </div>
      {error && <div className="session-tree-error">{error}</div>}

      {aiSettingsOpen && <AISettingsDialog onClose={() => setAiSettingsOpen(false)} />}

      <div className="session-tree-body">
        {roots.map((node) => (
          <FolderNode
            key={node.folder.id}
            node={node}
            onFolderContextMenu={openFolderContextMenu}
            onHostContextMenu={openHostContextMenu}
            onMoveFolder={moveFolder}
            onMoveHost={moveHost}
            onConnect={openTab}
          />
        ))}
        {rootHosts.map((host) => (
          <HostNode key={host.id} host={host} onContextMenu={openHostContextMenu} onConnect={openTab} />
        ))}
        {roots.length === 0 && rootHosts.length === 0 && (
          <div className="session-tree-empty">Right-click to add a folder or host.</div>
        )}
      </div>

      {contextMenu && <TreeContextMenu {...contextMenu} onClose={() => setContextMenu(null)} />}

      {folderDialog && (
        <FolderFormDialog
          mode={folderDialog.mode}
          initialName={folderDialog.folder?.name}
          onCancel={() => setFolderDialog(null)}
          onSubmit={async (name) => {
            if (folderDialog.mode === 'create') {
              await createFolder({ name, parent_id: folderDialog.parentId })
            } else {
              await renameFolder(folderDialog.folder!.id, { name })
            }
            setFolderDialog(null)
          }}
        />
      )}

      {hostDialog && (
        <HostFormDialog
          host={hostDialog.host}
          onCancel={() => setHostDialog(null)}
          onSubmit={async (input) => {
            if (hostDialog.host) {
              await updateHost(hostDialog.host.id, input as HostUpdateInput)
            } else {
              await createHost({ ...(input as HostCreateInput), folder_id: hostDialog.parentId })
            }
            setHostDialog(null)
          }}
        />
      )}
    </div>
  )
}
