import type { DragEvent } from 'react'

export type DragPayload = { type: 'folder' | 'host'; id: number }

// Moves a dropped item to the end of the target folder's children; the
// server clamps out-of-range indexes (see crud.sort_order_for_index), so a
// large sentinel is a simple, always-valid way to say "append at the end"
// without the client needing to know the target's current child count.
export const APPEND_INDEX = Number.MAX_SAFE_INTEGER

const MIME = 'application/x-savr-node'

export function makeDraggable(payload: DragPayload) {
  return {
    draggable: true,
    onDragStart: (e: DragEvent) => {
      e.dataTransfer.setData(MIME, JSON.stringify(payload))
      e.dataTransfer.effectAllowed = 'move'
    },
  }
}

export function makeDropTarget(onDrop: (payload: DragPayload) => void) {
  return {
    onDragOver: (e: DragEvent) => {
      if (e.dataTransfer.types.includes(MIME)) {
        e.preventDefault()
        e.dataTransfer.dropEffect = 'move'
      }
    },
    onDrop: (e: DragEvent) => {
      const raw = e.dataTransfer.getData(MIME)
      if (!raw) return
      e.preventDefault()
      e.stopPropagation()
      onDrop(JSON.parse(raw) as DragPayload)
    },
  }
}
