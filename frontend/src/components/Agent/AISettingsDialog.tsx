import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../../api/client'
import { Dialog } from '../HostDialog/Dialog'

interface AISettingsDialogProps {
  onClose: () => void
}

export function AISettingsDialog({ onClose }: AISettingsDialogProps) {
  const [loaded, setLoaded] = useState(false)
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [models, setModels] = useState<string[]>([])
  const [modelsError, setModelsError] = useState<string | null>(null)
  const [loadingModels, setLoadingModels] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.getAISettings().then((settings) => {
      setBaseUrl(settings.ollama_base_url)
      setModel(settings.ollama_model)
      setLoaded(true)
    })
  }, [])

  const refreshModels = async () => {
    setLoadingModels(true)
    setModelsError(null)
    try {
      const { models } = await api.listOllamaModels(baseUrl)
      setModels(models)
      if (models.length > 0 && !models.includes(model)) {
        setModel(models[0])
      }
    } catch (err) {
      setModelsError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoadingModels(false)
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      await api.updateAISettings({ ollama_base_url: baseUrl, ollama_model: model })
      onClose()
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  if (!loaded) {
    return (
      <Dialog title="AI Plugin Settings" onClose={onClose}>
        <p>Loading…</p>
      </Dialog>
    )
  }

  return (
    <Dialog title="AI Plugin Settings" onClose={onClose}>
      <form onSubmit={handleSubmit}>
        <label>
          Provider
          <select value="ollama" disabled>
            <option value="ollama">Ollama (local)</option>
          </select>
        </label>

        <label>
          Ollama base URL
          <input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="http://localhost:11434"
          />
        </label>

        <div className="ai-settings-fetch-row">
          <button type="button" onClick={refreshModels} disabled={loadingModels || !baseUrl.trim()}>
            {loadingModels ? 'Checking…' : 'Fetch available models'}
          </button>
        </div>

        {modelsError && <div className="agent-error">{modelsError}</div>}

        <label>
          Model
          {models.length > 0 ? (
            <select value={model} onChange={(e) => setModel(e.target.value)}>
              {models.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          ) : (
            <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="e.g. qwen3:8b" />
          )}
        </label>

        <div className="dialog-actions">
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" disabled={saving || !baseUrl.trim() || !model.trim()}>
            Save
          </button>
        </div>
      </form>
    </Dialog>
  )
}
