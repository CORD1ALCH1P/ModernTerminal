import { useEffect, useRef, useState, type FormEvent } from 'react'
import { AISettingsDialog } from './AISettingsDialog'

function CopyIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  )
}

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
  // Mirrors `streaming`, read from the assistant_done handler below instead
  // of the state variable itself: React StrictMode's dev-only double-invoke
  // of state *updater* functions means an updater that also calls another
  // setState as a side effect (as this used to, appending to `entries` from
  // inside the setStreaming(text => ...) callback) runs that side effect
  // twice, silently duplicating the finished message. A plain ref mutation
  // isn't part of that purity-checking mechanism, so it isn't re-run.
  const streamingRef = useRef('')
  const [mode, setMode] = useState<Mode>('confirm')
  const [pending, setPending] = useState<PendingConfirmation | null>(null)
  const [connectionError, setConnectionError] = useState<string | null>(null)
  const [capabilityWarning, setCapabilityWarning] = useState<string | null>(null)
  const [inputText, setInputText] = useState('')
  const [busy, setBusy] = useState(false)
  const [thinking, setThinking] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null)
  const [reconnectKey, setReconnectKey] = useState(0)

  useEffect(() => {
    // Guards against a stale connection's callbacks firing after this effect
    // has already been cleaned up (e.g. React StrictMode's dev-only double
    // mount/unmount/mount of effects opens a first WebSocket, closes it
    // immediately, then opens a second -- without this guard, the first
    // socket's belated onerror could still flip this component's state even
    // though the second, surviving socket is connected and healthy).
    let cancelled = false

    // A fresh connection re-fetches the provider server-side (see
    // agent_ws.py), which is what picks up settings saved via the dialog
    // below -- reset any stale capability warning/error from the previous
    // connection so this doesn't look like the save didn't do anything.
    setCapabilityWarning(null)
    setConnectionError(null)
    streamingRef.current = ''
    setStreaming('')

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
          setThinking(false)
          streamingRef.current += msg.text
          setStreaming(streamingRef.current)
          break
        case 'tool_call':
          setThinking(false)
          setEntries((e) => [
            ...e,
            { kind: 'activity', text: `Running ${msg.name}(${JSON.stringify(msg.arguments)})` },
          ])
          break
        case 'tool_result':
          setEntries((e) => [...e, { kind: 'activity', text: `Result: ${msg.result}` }])
          break
        case 'pending_confirmation':
          setThinking(false)
          setPending({ command: msg.command, reason: msg.reason })
          break
        case 'assistant_done': {
          setThinking(false)
          // Captured by value: setEntries' updater only runs later, when
          // React gets around to processing it, by which point the
          // streamingRef.current = '' reset below would already have
          // happened if this read it live off the ref instead.
          const finalText = streamingRef.current
          if (finalText) {
            setEntries((e) => [...e, { kind: 'assistant', text: finalText }])
          }
          streamingRef.current = ''
          setStreaming('')
          setBusy(false)
          break
        }
        case 'mode_changed':
          setMode(msg.mode)
          break
        case 'capability_warning':
          setCapabilityWarning(msg.message)
          break
        case 'error':
          setThinking(false)
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
  }, [sessionId, reconnectKey])

  useEffect(() => {
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight })
  }, [entries, streaming, thinking])

  const sendUserMessage = (e: FormEvent) => {
    e.preventDefault()
    const text = inputText.trim()
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    setEntries((entries) => [...entries, { kind: 'user', text }])
    setBusy(true)
    setThinking(true)
    wsRef.current.send(JSON.stringify({ type: 'user_message', text }))
    setInputText('')
  }

  const respondToConfirmation = (approve: boolean) => {
    wsRef.current?.send(JSON.stringify({ type: 'confirm_command', approve }))
    setPending(null)
  }

  const copyText = (text: string, index: number) => {
    void navigator.clipboard.writeText(text)
    setCopiedIndex(index)
    window.setTimeout(() => setCopiedIndex((cur) => (cur === index ? null : cur)), 1200)
  }

  const changeMode = (newMode: Mode) => {
    wsRef.current?.send(JSON.stringify({ type: 'set_mode', mode: newMode }))
  }

  // Saving settings updates the backend's provider, but this panel's WS
  // connection already fetched (and is holding onto) the *old* provider
  // instance for its whole lifetime -- reconnecting is what picks up the
  // change immediately instead of leaving a stale "model not found" banner
  // up until the user manually closes and reopens the panel/session.
  const reconnectAfterSettingsSaved = () => setReconnectKey((k) => k + 1)

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

      {settingsOpen && (
        <AISettingsDialog
          onClose={() => setSettingsOpen(false)}
          onSaved={reconnectAfterSettingsSaved}
        />
      )}

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
              <button
                type="button"
                className="agent-message-copy"
                title="Copy"
                aria-label="Copy message"
                onClick={() => copyText(entry.text, i)}
              >
                {copiedIndex === i ? <CheckIcon /> : <CopyIcon />}
              </button>
            </div>
          ),
        )}
        {streaming && <div className="agent-message agent-message--assistant">{streaming}</div>}
        {thinking && (
          <div className="agent-message agent-message--assistant agent-message--thinking">
            <span className="thinking-dots">
              <span />
              <span />
              <span />
            </span>
          </div>
        )}
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
