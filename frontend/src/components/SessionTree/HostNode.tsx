import type { MouseEvent } from 'react'
import type { Host } from '../../api/types'
import { makeDraggable } from './useDragAndDrop'

interface HostNodeProps {
  host: Host
  onContextMenu: (e: MouseEvent, host: Host) => void
  onConnect: (host: Host) => void
}

export function HostNode({ host, onContextMenu, onConnect }: HostNodeProps) {
  const drag = makeDraggable({ type: 'host', id: host.id })

  return (
    <div
      className="host-row"
      {...drag}
      onDoubleClick={() => onConnect(host)}
      onContextMenu={(e) => onContextMenu(e, host)}
      title="Double-click to connect"
    >
      <span className={`protocol-badge protocol-badge--${host.protocol}`}>{host.protocol}</span>
      <span className="host-label">{host.label}</span>
      <span className="host-address">
        {host.hostname}:{host.port}
      </span>
    </div>
  )
}
