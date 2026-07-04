import { useEffect } from 'react'

export interface MenuItem {
  label: string
  onClick: () => void
  danger?: boolean
}

export interface TreeContextMenuProps {
  x: number
  y: number
  items: MenuItem[]
  onClose: () => void
}

export function TreeContextMenu({ x, y, items, onClose }: TreeContextMenuProps) {
  useEffect(() => {
    // Deferred by a tick: React flushes effects synchronously for discrete
    // native events like this one's own opening "contextmenu" event, which is
    // still bubbling to window when this effect runs. Attaching the listener
    // immediately would let it catch that same event and close the menu
    // instantly; deferring to the next tick lets the current dispatch finish.
    const timer = window.setTimeout(() => {
      window.addEventListener('click', onClose)
      window.addEventListener('contextmenu', onClose)
    }, 0)
    return () => {
      window.clearTimeout(timer)
      window.removeEventListener('click', onClose)
      window.removeEventListener('contextmenu', onClose)
    }
  }, [onClose])

  return (
    <ul className="tree-context-menu" style={{ top: y, left: x }} onClick={(e) => e.stopPropagation()}>
      {items.map((item) => (
        <li
          key={item.label}
          className={item.danger ? 'danger' : undefined}
          onClick={() => {
            item.onClick()
            onClose()
          }}
        >
          {item.label}
        </li>
      ))}
    </ul>
  )
}
