import type {
  AISettings,
  AISettingsUpdateInput,
  Folder,
  FolderCreateInput,
  FolderMoveInput,
  FolderRenameInput,
  Host,
  HostCreateInput,
  HostMoveInput,
  HostUpdateInput,
} from './types'

const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}${body ? `: ${body}` : ''}`)
  }
  if (res.status === 204) {
    return undefined as T
  }
  return (await res.json()) as T
}

export const api = {
  listFolders: () => request<Folder[]>('/folders'),
  createFolder: (input: FolderCreateInput) =>
    request<Folder>('/folders', { method: 'POST', body: JSON.stringify(input) }),
  renameFolder: (id: number, input: FolderRenameInput) =>
    request<Folder>(`/folders/${id}`, { method: 'PATCH', body: JSON.stringify(input) }),
  moveFolder: (id: number, input: FolderMoveInput) =>
    request<Folder>(`/folders/${id}/move`, { method: 'PATCH', body: JSON.stringify(input) }),
  deleteFolder: (id: number) => request<void>(`/folders/${id}`, { method: 'DELETE' }),

  listHosts: () => request<Host[]>('/hosts'),
  createHost: (input: HostCreateInput) =>
    request<Host>('/hosts', { method: 'POST', body: JSON.stringify(input) }),
  updateHost: (id: number, input: HostUpdateInput) =>
    request<Host>(`/hosts/${id}`, { method: 'PATCH', body: JSON.stringify(input) }),
  moveHost: (id: number, input: HostMoveInput) =>
    request<Host>(`/hosts/${id}/move`, { method: 'PATCH', body: JSON.stringify(input) }),
  deleteHost: (id: number) => request<void>(`/hosts/${id}`, { method: 'DELETE' }),
  acceptHostKey: (id: number, fingerprint: string) =>
    request<Host>(`/hosts/${id}/accept-host-key`, {
      method: 'POST',
      body: JSON.stringify({ fingerprint }),
    }),

  getAISettings: () => request<AISettings>('/ai/settings'),
  updateAISettings: (input: AISettingsUpdateInput) =>
    request<AISettings>('/ai/settings', { method: 'PUT', body: JSON.stringify(input) }),
  listOllamaModels: (baseUrl: string) =>
    request<{ models: string[] }>(`/ai/models?base_url=${encodeURIComponent(baseUrl)}`),
}
