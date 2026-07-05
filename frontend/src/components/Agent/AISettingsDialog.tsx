import { useEffect, useState, type FormEvent } from 'react'
import type { AIProviderKind } from '../../api/types'
import { api } from '../../api/client'
import { Dialog } from '../HostDialog/Dialog'

interface AISettingsDialogProps {
  onClose: () => void
  // Called right after a successful save, before onClose -- lets a caller
  // that already has an open agent connection (which captured the *old*
  // provider for its whole lifetime) reconnect immediately instead of the
  // fix only taking effect on the next manual close/reopen.
  onSaved?: () => void
}

export function AISettingsDialog({ onClose, onSaved }: AISettingsDialogProps) {
  const [loaded, setLoaded] = useState(false)
  const [provider, setProvider] = useState<AIProviderKind>('ollama')

  const [ollamaBaseUrl, setOllamaBaseUrl] = useState('')
  const [ollamaModel, setOllamaModel] = useState('')
  const [models, setModels] = useState<string[]>([])
  const [modelsError, setModelsError] = useState<string | null>(null)
  const [loadingModels, setLoadingModels] = useState(false)

  const [customApiBaseUrl, setCustomApiBaseUrl] = useState('')
  const [customApiModel, setCustomApiModel] = useState('')
  const [customApiKey, setCustomApiKey] = useState('')
  const [hasCustomApiKey, setHasCustomApiKey] = useState(false)

  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.getAISettings().then((settings) => {
      setProvider(settings.provider)
      setOllamaBaseUrl(settings.ollama_base_url)
      setOllamaModel(settings.ollama_model)
      setCustomApiBaseUrl(settings.custom_api_base_url)
      setCustomApiModel(settings.custom_api_model)
      setHasCustomApiKey(settings.has_custom_api_key)
      setLoaded(true)
    })
  }, [])

  const refreshModels = async () => {
    setLoadingModels(true)
    setModelsError(null)
    try {
      const { models } = await api.listOllamaModels(ollamaBaseUrl)
      setModels(models)
      if (models.length > 0 && !models.includes(ollamaModel)) {
        setOllamaModel(models[0])
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
      if (provider === 'ollama') {
        await api.updateAISettings({
          provider,
          ollama_base_url: ollamaBaseUrl,
          ollama_model: ollamaModel,
        })
      } else {
        await api.updateAISettings({
          provider,
          custom_api_base_url: customApiBaseUrl,
          custom_api_model: customApiModel,
          ...(customApiKey.trim() ? { custom_api_key: customApiKey.trim() } : {}),
        })
      }
      onSaved?.()
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

  const canSave =
    provider === 'ollama'
      ? ollamaBaseUrl.trim() && ollamaModel.trim()
      : customApiBaseUrl.trim() && customApiModel.trim()

  return (
    <Dialog title="AI Plugin Settings" onClose={onClose}>
      <form onSubmit={handleSubmit}>
        <label>
          Provider
          <select value={provider} onChange={(e) => setProvider(e.target.value as AIProviderKind)}>
            <option value="ollama">Ollama (local)</option>
            <option value="custom_api">Custom API (OpenAI-compatible)</option>
          </select>
        </label>

        {provider === 'ollama' ? (
          <>
            <label>
              Ollama base URL
              <input
                value={ollamaBaseUrl}
                onChange={(e) => setOllamaBaseUrl(e.target.value)}
                placeholder="http://localhost:11434"
              />
            </label>

            <div className="ai-settings-fetch-row">
              <button
                type="button"
                onClick={refreshModels}
                disabled={loadingModels || !ollamaBaseUrl.trim()}
              >
                {loadingModels ? 'Checking…' : 'Fetch available models'}
              </button>
            </div>

            {modelsError && <div className="agent-error">{modelsError}</div>}

            <label>
              Model
              {models.length > 0 ? (
                <select value={ollamaModel} onChange={(e) => setOllamaModel(e.target.value)}>
                  {models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  value={ollamaModel}
                  onChange={(e) => setOllamaModel(e.target.value)}
                  placeholder="e.g. qwen3:8b"
                />
              )}
            </label>
          </>
        ) : (
          <>
            <label>
              API base URL
              <input
                value={customApiBaseUrl}
                onChange={(e) => setCustomApiBaseUrl(e.target.value)}
                placeholder="https://api.example.com/v1"
              />
              <span className="hint">Include any version prefix the server expects.</span>
            </label>

            <label>
              Model
              <input
                value={customApiModel}
                onChange={(e) => setCustomApiModel(e.target.value)}
                placeholder="e.g. gpt-4o-mini"
              />
            </label>

            <label>
              API key
              <input
                type="password"
                value={customApiKey}
                onChange={(e) => setCustomApiKey(e.target.value)}
                placeholder={hasCustomApiKey ? '•••••••• (leave blank to keep)' : 'sk-...'}
              />
              <span className="hint">
                {hasCustomApiKey
                  ? 'A key is already saved -- only fill this in to replace it.'
                  : 'Left blank if the server does not require one.'}
              </span>
            </label>
          </>
        )}

        <div className="dialog-actions">
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" disabled={saving || !canSave}>
            Save
          </button>
        </div>
      </form>
    </Dialog>
  )
}
