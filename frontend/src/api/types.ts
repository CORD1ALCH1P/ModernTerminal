export type Protocol = 'ssh' | 'telnet'
export type AuthMethod = 'password' | 'private_key' | 'none'

export interface Folder {
  id: number
  parent_id: number | null
  name: string
  sort_order: number
  created_at: string
  updated_at: string
}

export interface Host {
  id: number
  folder_id: number | null
  label: string
  protocol: Protocol
  hostname: string
  port: number
  username: string | null
  auth_method: AuthMethod
  has_secret: boolean
  ssh_host_key_fingerprint: string | null
  legacy_crypto: boolean
  notes: string | null
  sort_order: number
  created_at: string
  updated_at: string
}

export interface FolderCreateInput {
  name: string
  parent_id?: number | null
}

export interface FolderRenameInput {
  name: string
}

export interface FolderMoveInput {
  parent_id: number | null
  index: number
}

export interface HostCreateInput {
  label: string
  folder_id?: number | null
  protocol: Protocol
  hostname: string
  port?: number
  username?: string | null
  auth_method?: AuthMethod
  secret?: string
  passphrase?: string
  legacy_crypto?: boolean
  notes?: string | null
}

export interface HostUpdateInput {
  label?: string
  hostname?: string
  port?: number
  username?: string | null
  auth_method?: AuthMethod
  secret?: string
  passphrase?: string
  legacy_crypto?: boolean
  notes?: string | null
}

export interface HostMoveInput {
  folder_id: number | null
  index: number
}

export type AIProviderKind = 'ollama' | 'custom_api'

export interface AISettings {
  provider: AIProviderKind
  ollama_base_url: string
  ollama_model: string
  custom_api_base_url: string
  custom_api_model: string
  has_custom_api_key: boolean
}

export interface AISettingsUpdateInput {
  provider?: AIProviderKind
  ollama_base_url?: string
  ollama_model?: string
  custom_api_base_url?: string
  custom_api_model?: string
  custom_api_key?: string
}
