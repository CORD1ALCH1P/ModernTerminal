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
  notes?: string | null
}

export interface HostMoveInput {
  folder_id: number | null
  index: number
}

export interface AISettings {
  provider: string
  ollama_base_url: string
  ollama_model: string
}

export interface AISettingsUpdateInput {
  ollama_base_url?: string
  ollama_model?: string
}
