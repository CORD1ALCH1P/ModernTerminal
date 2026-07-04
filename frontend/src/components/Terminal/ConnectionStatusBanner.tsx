import type { ReactNode } from 'react'

export type ConnectionState = 'connecting' | 'connected' | 'error' | 'closed'

interface ConnectionStatusBannerProps {
  state: ConnectionState
  message: string | null
  actions?: ReactNode
}

export function ConnectionStatusBanner({ state, message, actions }: ConnectionStatusBannerProps) {
  return (
    <div className={`terminal-status terminal-status--${state}`}>
      <span>
        {state}
        {message ? ` — ${message}` : ''}
      </span>
      {actions && <span className="terminal-status-actions">{actions}</span>}
    </div>
  )
}
