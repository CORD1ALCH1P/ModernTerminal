import type { MouseEvent, ReactNode } from 'react'

interface DialogProps {
  title: string
  children: ReactNode
  onClose: () => void
}

export function Dialog({ title, children, onClose }: DialogProps) {
  const stop = (e: MouseEvent) => e.stopPropagation()
  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog-box" onClick={stop}>
        <h2>{title}</h2>
        {children}
      </div>
    </div>
  )
}
