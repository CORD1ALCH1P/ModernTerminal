import { useState, type FormEvent } from 'react'
import { Dialog } from './Dialog'

interface FolderFormDialogProps {
  mode: 'create' | 'rename'
  initialName?: string
  onSubmit: (name: string) => void | Promise<void>
  onCancel: () => void
}

export function FolderFormDialog({ mode, initialName, onSubmit, onCancel }: FolderFormDialogProps) {
  const [name, setName] = useState(initialName ?? '')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return
    setSubmitting(true)
    try {
      await onSubmit(trimmed)
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog title={mode === 'create' ? 'New Folder' : 'Rename Folder'} onClose={onCancel}>
      <form onSubmit={handleSubmit}>
        <label>
          Name
          <input autoFocus value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <div className="dialog-actions">
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
          <button type="submit" disabled={submitting || !name.trim()}>
            {mode === 'create' ? 'Create' : 'Rename'}
          </button>
        </div>
      </form>
    </Dialog>
  )
}
