import { useEffect, useRef, useState } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { useSessionTree } from '../../state/SessionTreeContext'
import { ConnectionStatusBanner, type ConnectionState } from './ConnectionStatusBanner'
import { createOutputHighlighter } from './outputHighlighter'

type ControlMessage =
  | { type: 'status'; state: 'connecting' | 'connected'; note?: string }
  | { type: 'error'; message: string; fatal: boolean; fingerprint?: string }
  | { type: 'closed'; reason: string }

// Grace period so the banner explaining why the session ended (e.g. "closed
// -- Connection closed by remote host") is visible for a moment before the
// tab disappears, instead of vanishing the instant the connection drops.
const AUTO_CLOSE_DELAY_MS = 1500

interface TerminalPaneProps {
  hostId: number
  isActive: boolean
  sessionId: string
  aiPanelOpen: boolean
  onToggleAgentPanel: () => void
  onSessionEnded: () => void
}

export function TerminalPane({
  hostId,
  isActive,
  sessionId,
  aiPanelOpen,
  onToggleAgentPanel,
  onSessionEnded,
}: TerminalPaneProps) {
  const { acceptHostKey } = useSessionTree()
  const containerRef = useRef<HTMLDivElement>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const [state, setState] = useState<ConnectionState>('connecting')
  const [message, setMessage] = useState<string | null>(null)
  const [mismatchFingerprint, setMismatchFingerprint] = useState<string | null>(null)
  const [reconnectKey, setReconnectKey] = useState(0)

  // Latest-ref indirection so the connection effect below doesn't need
  // onSessionEnded in its dependency array -- TerminalTabs passes a new
  // inline closure on every render, and this effect must only re-run for an
  // actual new connection attempt (host/session/reconnect change), not on
  // every parent re-render.
  const onSessionEndedRef = useRef(onSessionEnded)
  useEffect(() => {
    onSessionEndedRef.current = onSessionEnded
  }, [onSessionEnded])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    // Guards against a stale connection's callbacks firing after this effect
    // has already been cleaned up (e.g. React StrictMode's dev-only double
    // mount/unmount/mount of effects opens a first WebSocket, closes it
    // immediately, then opens a second -- without this guard, the first
    // socket's belated onerror/onmessage could still flip this component's
    // state even though the second, surviving socket is connected and healthy).
    let cancelled = false

    setState('connecting')
    setMessage(null)
    setMismatchFingerprint(null)

    const term = new Terminal({ cursorBlink: true, convertEol: true })
    const fitAddon = new FitAddon()
    fitAddonRef.current = fitAddon
    term.loadAddon(fitAddon)
    term.open(container)

    // The default renderer is canvas-based and always works; WebGL is a
    // pure perf upgrade on top of it, so a failure here must not break
    // rendering -- just skip the addon.
    void import('@xterm/addon-webgl')
      .then(({ WebglAddon }) => term.loadAddon(new WebglAddon()))
      .catch(() => {
        /* fall back to the default canvas renderer */
      })

    fitAddon.fit()

    const highlight = createOutputHighlighter()

    // A session that never reached "connected" failed to establish (bad
    // credentials, host-key mismatch, unreachable host) and needs the user's
    // attention (fix the host, accept the new key, etc.), so it's left open.
    // A session that WAS live and then ended -- remote closed it, network
    // dropped -- is auto-closed instead, whether that end was deliberate
    // (the user typed `exit`) or not.
    let hasConnected = false
    let ended = false
    let autoCloseTimeout: number | null = null

    const scheduleAutoCloseIfLive = () => {
      if (ended) return
      ended = true
      if (!hasConnected) return
      autoCloseTimeout = window.setTimeout(() => {
        if (!cancelled) onSessionEndedRef.current()
      }, AUTO_CLOSE_DELAY_MS)
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(
      `${protocol}//${window.location.host}/api/ws/terminal?host_id=${hostId}&cols=${term.cols}&rows=${term.rows}&session_id=${sessionId}`,
    )
    ws.binaryType = 'arraybuffer'

    ws.onmessage = (event) => {
      if (cancelled) return
      if (event.data instanceof ArrayBuffer) {
        term.write(highlight(new Uint8Array(event.data)))
        return
      }
      const control = JSON.parse(event.data) as ControlMessage
      if (control.type === 'status') {
        setState(control.state)
        setMessage(control.note ?? null)
        if (control.state === 'connected') hasConnected = true
      } else if (control.type === 'error') {
        setState('error')
        setMessage(control.message)
        setMismatchFingerprint(control.fingerprint ?? null)
        scheduleAutoCloseIfLive()
      } else if (control.type === 'closed') {
        setState('closed')
        setMessage(control.reason)
        scheduleAutoCloseIfLive()
      }
    }
    ws.onerror = () => {
      if (cancelled) return
      setState('error')
      scheduleAutoCloseIfLive()
    }
    ws.onclose = () => {
      if (cancelled) return
      // Fallback for a drop severe enough that no "error"/"closed" control
      // message ever arrived (e.g. the network path itself died). Every
      // other path above already called scheduleAutoCloseIfLive, so this is
      // a no-op then; it only does something for that one uncovered case.
      if (!ended) {
        setState('closed')
        setMessage('Connection lost')
      }
      scheduleAutoCloseIfLive()
    }

    const dataDisposable = term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(new TextEncoder().encode(data))
      }
    })

    const resizeDisposable = term.onResize(({ cols, rows }) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'resize', cols, rows }))
      }
    })

    const handleWindowResize = () => fitAddon.fit()
    window.addEventListener('resize', handleWindowResize)

    return () => {
      cancelled = true
      if (autoCloseTimeout !== null) clearTimeout(autoCloseTimeout)
      window.removeEventListener('resize', handleWindowResize)
      dataDisposable.dispose()
      resizeDisposable.dispose()
      ws.close()
      term.dispose()
      fitAddonRef.current = null
    }
  }, [hostId, sessionId, reconnectKey])

  // Background tabs stay mounted (and connected) so switching tabs doesn't
  // kill the session; re-fit on becoming visible since xterm can't measure
  // its container accurately while it's display:none. Also re-fit when the
  // AI panel opens/closes: that resizes this pane's flex sibling without a
  // window "resize" event, so xterm's canvas would otherwise stay sized for
  // the old (wider) width and visually overlap the agent panel.
  useEffect(() => {
    if (isActive) fitAddonRef.current?.fit()
  }, [isActive, aiPanelOpen])

  const reconnect = () => setReconnectKey((k) => k + 1)

  const actions = (
    <>
      {mismatchFingerprint && (
        <button
          type="button"
          onClick={async () => {
            await acceptHostKey(hostId, mismatchFingerprint)
            reconnect()
          }}
        >
          Accept new key &amp; reconnect
        </button>
      )}
      {(state === 'error' || state === 'closed') && (
        <button type="button" onClick={reconnect}>
          Reconnect
        </button>
      )}
      <button type="button" disabled={state !== 'connected'} onClick={onToggleAgentPanel}>
        {aiPanelOpen ? 'Hide AI Plugin' : 'AI Plugin'}
      </button>
    </>
  )

  return (
    <div className="terminal-pane">
      <ConnectionStatusBanner state={state} message={message} actions={actions} />
      <div ref={containerRef} className="terminal-container" />
    </div>
  )
}
