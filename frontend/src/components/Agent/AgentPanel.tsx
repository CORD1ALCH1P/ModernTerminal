import { useEffect, useRef, useState, type FormEvent } from 'react'
import { AISettingsDialog } from './AISettingsDialog'

type Mode = 'confirm' | 'auto'

interface ChatEntry {
  kind: 'user' | 'assistant' | 'activity'
  text: string
}

interface PendingConfirmation {
  command: string
  reason: 'dangerous' | 'confirm_mode'
}

interface AgentPanelProps {
  sessionId: string
}

export function AgentPanel({ sessionId }: AgentPanelProps) {
  const wsRef = useRef<WebSocket | null>(null)
  const messagesRef = useRef<HTMLDivElement>(null)
  const [entries, setEntries] = useState<ChatEntry[]>([])
  const [streaming, setStreaming] = useState('')
  const [mode, setMode] = useState<Mode>('confirm')
  const [pending, setPending] = useState<PendingConfirmation | null>(null)
  const [connectionError, setConnectionError] = useState<string | null>(null)
  const [capabilityWarning, setCapabilityWarning] = useState<string | null>(null)
  const [inputText, setInputText] = useState('')
  const [busy, setBusy] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)

  useEffect(() => {
    // Guards against a stale connection's callbacks firing after this effect
    // has already been cleaned up (e.g. React StrictMode's dev-only double
    // mount/unmount/mount of effects opens a first WebSocket, closes it
    // immediately, then opens a second -- without this guard, the first
    // socket's belated onerror could still flip this component's state even
    // though the second, surviving socket is connected and healthy).
    let cancelled = false

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(
      `${protocol}//${window.location.host}/api/ws/agent?session_id=${sessionId}`,
    )
    wsRef.current = ws

    ws.onmessage = (event) => {
      if (cancelled) return
      const msg = JSON.parse(event.data)
      switch (msg.type) {
        case 'status':
          setMode(msg.mode)
          break
        case 'history':
          setEntries(
            (msg.messages as { role: string; content: string }[])
              .filter((m) => m.role === 'user' || m.role === 'assistant')
              .map((m) => ({ kind: m.role as 'user' | 'assistant', text: m.content })),
          )
          break
        case 'assistant_delta':
          setStreaming((text) => text + msg.text)
          break
        case 'tool_call':
          setEntries((e) => [
            ...e,
            { kind: 'activity', text: `Running ${msg.name}(${JSON.stringify(msg.arguments)})` },
          ])
          break
        case 'tool_result':
          setEntries((e) => [...e, { kind: 'activity', text: `Result: ${msg.result}` }])
          break
        case 'pending_confirmation':
          setPending({ command: msg.command, reason: msg.reason })
          break
        case 'assistant_done':
          setStreaming((text) => {
            if (text) setEntries((e) => [...e, { kind: 'assistant', text }])
            return ''
          })
          setBusy(false)
          break
        case 'mode_changed':
          setMode(msg.mode)
          break
        case 'capability_warning':
          setCapabilityWarning(msg.message)
          break
        case 'error':
          setConnectionError(msg.message)
          if (msg.fatal) setBusy(false)
          break
      }
    }
    ws.onerror = () => {
      if (cancelled) return
      setConnectionError('Connection error')
    }

    return () => {
      cancelled = true
      ws.close()
    }
  }, [sessionId])

  useEffect(() => {
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight })
  }, [entries, streaming])

  const sendUserMessage = (e: FormEvent) => {
    e.preventDefault()
    const text = inputText.trim()
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    setEntries((entries) => [...entries, { kind: 'user', text }])
    setBusy(true)
    wsRef.current.send(JSON.stringify({ type: 'user_message', text }))
    setInputText('')
  }

  const respondToConfirmation = (approve: boolean) => {
    wsRef.current?.send(JSON.stringify({ type: 'confirm_command', approve }))
    setPending(null)
  }

  const changeMode = (newMode: Mode) => {
    wsRef.current?.send(JSON.stringify({ type: 'set_mode', mode: newMode }))
  }

  return (
    <div className="agent-panel">
      <div className="agent-header">
        <span>AI Plugin</span>
        <div className="agent-header-actions">
          <select value={mode} onChange={(e) => changeMode(e.target.value as Mode)}>
            <option value="confirm">Confirm before applying</option>
            <option value="auto">Auto-apply</option>
          </select>
          <button type="button" onClick={() => setSettingsOpen(true)}>
            Settings
          </button>
        </div>
      </div>

      {settingsOpen && <AISettingsDialog onClose={() => setSettingsOpen(false)} />}

      {connectionError && <div className="agent-error">{connectionError}</div>}
      {capabilityWarning && <div className="agent-capability-warning">{capabilityWarning}</div>}

      <div className="agent-messages" ref={messagesRef}>
        {entries.map((entry, i) =>
          entry.kind === 'activity' ? (
            <div key={i} className="agent-tool-activity">
              {entry.text}
            </div>
          ) : (
            <div key={i} className={`agent-message agent-message--${entry.kind}`}>
              {entry.text}
            </div>
          ),
        )}
        {streaming && <div className="agent-message agent-message--assistant">{streaming}</div>}
      </div>

      {pending && (
        <div className="agent-pending-confirmation">
          <div>
            Run command: <code>{pending.command}</code>
          </div>
          <div className="hint">
            {pending.reason === 'dangerous'
              ? 'Flagged as potentially dangerous.'
              : 'Confirm-before-apply mode is on.'}
          </div>
          <div className="dialog-actions">
            <button type="button" onClick={() => respondToConfirmation(false)}>
              Reject
            </button>
            <button type="button" onClick={() => respondToConfirmation(true)}>
              Approve
            </button>
          </div>
        </div>
      )}

      <form className="agent-input-row" onSubmit={sendUserMessage}>
        <input
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder="Ask the AI plugin…"
          disabled={busy}
        />
        <button type="submit" disabled={busy || !inputText.trim()}>
          Send
        </button>
      </form>
    </div>
  )
}
