import { useState, type FormEvent } from 'react'
import type { AuthMethod, Host, HostCreateInput, HostUpdateInput, Protocol } from '../../api/types'
import { Dialog } from './Dialog'

interface HostFormDialogProps {
  host?: Host
  onSubmit: (input: HostCreateInput | HostUpdateInput) => void | Promise<void>
  onCancel: () => void
}

export function HostFormDialog({ host, onSubmit, onCancel }: HostFormDialogProps) {
  const isEdit = Boolean(host)
  const [label, setLabel] = useState(host?.label ?? '')
  const [protocol, setProtocol] = useState<Protocol>(host?.protocol ?? 'ssh')
  const [hostname, setHostname] = useState(host?.hostname ?? '')
  const [port, setPort] = useState(host ? String(host.port) : '')
  const [username, setUsername] = useState(host?.username ?? '')
  const [authMethod, setAuthMethod] = useState<AuthMethod>(
    host?.auth_method ?? (protocol === 'ssh' ? 'password' : 'none'),
  )
  const [secret, setSecret] = useState('')
  const [passphrase, setPassphrase] = useState('')
  const [notes, setNotes] = useState(host?.notes ?? '')
  const [submitting, setSubmitting] = useState(false)

  const effectiveProtocol = isEdit ? host!.protocol : protocol
  const requiresSecret = authMethod === 'password' || authMethod === 'private_key'

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      const base = {
        label: label.trim(),
        hostname: hostname.trim(),
        port: port ? Number(port) : undefined,
        username: username.trim() || null,
        auth_method: authMethod,
        notes: notes.trim() || null,
        ...(secret ? { secret, passphrase: passphrase || undefined } : {}),
      }
      if (isEdit) {
        await onSubmit(base)
      } else {
        await onSubmit({ ...base, protocol } as HostCreateInput)
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog title={isEdit ? `Edit ${host!.label}` : 'New Host'} onClose={onCancel}>
      <form onSubmit={handleSubmit}>
        <label>
          Label
          <input autoFocus value={label} onChange={(e) => setLabel(e.target.value)} required />
        </label>

        {!isEdit && (
          <label>
            Protocol
            <select
              value={protocol}
              onChange={(e) => {
                const p = e.target.value as Protocol
                setProtocol(p)
                setAuthMethod(p === 'ssh' ? 'password' : 'none')
              }}
            >
              <option value="ssh">SSH</option>
              <option value="telnet">Telnet</option>
            </select>
          </label>
        )}

        <label>
          Hostname
          <input value={hostname} onChange={(e) => setHostname(e.target.value)} required />
        </label>

        <label>
          Port
          <input
            type="number"
            min={1}
            max={65535}
            value={port}
            onChange={(e) => setPort(e.target.value)}
            placeholder={effectiveProtocol === 'ssh' ? '22' : '23'}
          />
        </label>

        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>

        {effectiveProtocol === 'ssh' && (
          <label>
            Auth method
            <select value={authMethod} onChange={(e) => setAuthMethod(e.target.value as AuthMethod)}>
              <option value="password">Password</option>
              <option value="private_key">Private key</option>
            </select>
          </label>
        )}

        {requiresSecret && (
          <label>
            {authMethod === 'private_key' ? 'Private key (PEM)' : 'Password'}
            {isEdit && <span className="hint"> — leave blank to keep the current one</span>}
            {authMethod === 'private_key' ? (
              <textarea value={secret} onChange={(e) => setSecret(e.target.value)} rows={4} />
            ) : (
              <input type="password" value={secret} onChange={(e) => setSecret(e.target.value)} />
            )}
          </label>
        )}

        {authMethod === 'private_key' && (
          <label>
            Passphrase (optional)
            <input type="password" value={passphrase} onChange={(e) => setPassphrase(e.target.value)} />
          </label>
        )}

        <label>
          Notes
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
        </label>

        <div className="dialog-actions">
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
          <button type="submit" disabled={submitting || !label.trim() || !hostname.trim()}>
            {isEdit ? 'Save' : 'Create'}
          </button>
        </div>
      </form>
    </Dialog>
  )
}
