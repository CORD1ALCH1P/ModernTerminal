import { useState, type MouseEvent } from 'react'
import type { Folder, FolderMoveInput, Host, HostMoveInput } from '../../api/types'
import type { FolderTreeNode } from '../../state/buildTree'
import { HostNode } from './HostNode'
import { APPEND_INDEX, makeDraggable, makeDropTarget } from './useDragAndDrop'

interface FolderNodeProps {
  node: FolderTreeNode
  onFolderContextMenu: (e: MouseEvent, folder: Folder) => void
  onHostContextMenu: (e: MouseEvent, host: Host) => void
  onMoveFolder: (id: number, input: FolderMoveInput) => Promise<void>
  onMoveHost: (id: number, input: HostMoveInput) => Promise<void>
  onConnect: (host: Host) => void
}

export function FolderNode({
  node,
  onFolderContextMenu,
  onHostContextMenu,
  onMoveFolder,
  onMoveHost,
  onConnect,
}: FolderNodeProps) {
  const [expanded, setExpanded] = useState(true)
  const drag = makeDraggable({ type: 'folder', id: node.folder.id })
  const drop = makeDropTarget(async (payload) => {
    try {
      if (payload.type === 'folder') {
        if (payload.id === node.folder.id) return
        await onMoveFolder(payload.id, { parent_id: node.folder.id, index: APPEND_INDEX })
      } else {
        await onMoveHost(payload.id, { folder_id: node.folder.id, index: APPEND_INDEX })
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err))
    }
  })

  return (
    <div className="folder-node">
      <div
        className="folder-row"
        {...drag}
        {...drop}
        onClick={() => setExpanded((v) => !v)}
        onContextMenu={(e) => onFolderContextMenu(e, node.folder)}
      >
        <span className="chevron">{expanded ? '▼' : '▶'}</span>
        <span className="folder-name">{node.folder.name}</span>
      </div>
      {expanded && (
        <div className="folder-children">
          {node.children.map((child) => (
            <FolderNode
              key={child.folder.id}
              node={child}
              onFolderContextMenu={onFolderContextMenu}
              onHostContextMenu={onHostContextMenu}
              onMoveFolder={onMoveFolder}
              onMoveHost={onMoveHost}
              onConnect={onConnect}
            />
          ))}
          {node.hosts.map((host) => (
            <HostNode key={host.id} host={host} onContextMenu={onHostContextMenu} onConnect={onConnect} />
          ))}
        </div>
      )}
    </div>
  )
}
