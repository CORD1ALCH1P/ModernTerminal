import type { Folder, Host } from '../api/types'
import { buildTree, type FolderTreeNode } from './buildTree'

// Only non-secret fields -- the API never returns passwords/private keys in
// the first place (see HostOut in the backend), so there's nothing to
// deliberately strip there; this just drops DB-internal bookkeeping
// (ids, sort_order, timestamps, host-key fingerprint) that's noise for a
// human reading the export rather than the app itself.
interface ExportedHost {
  label: string
  protocol: Host['protocol']
  hostname: string
  port: number
  username: string | null
  auth_method: Host['auth_method']
  legacy_crypto: boolean
  notes: string | null
}

interface ExportedFolder {
  name: string
  folders: ExportedFolder[]
  hosts: ExportedHost[]
}

interface HostsExport {
  exported_at: string
  folders: ExportedFolder[]
  hosts: ExportedHost[]
}

function toExportedHost(host: Host): ExportedHost {
  return {
    label: host.label,
    protocol: host.protocol,
    hostname: host.hostname,
    port: host.port,
    username: host.username,
    auth_method: host.auth_method,
    legacy_crypto: host.legacy_crypto,
    notes: host.notes,
  }
}

function toExportedFolder(node: FolderTreeNode): ExportedFolder {
  return {
    name: node.folder.name,
    folders: node.children.map(toExportedFolder),
    hosts: node.hosts.map(toExportedHost),
  }
}

export function buildHostsExport(folders: Folder[], hosts: Host[]): HostsExport {
  const { roots, rootHosts } = buildTree(folders, hosts)
  return {
    exported_at: new Date().toISOString(),
    folders: roots.map(toExportedFolder),
    hosts: rootHosts.map(toExportedHost),
  }
}

export function downloadHostsExport(folders: Folder[], hosts: Host[]): void {
  const data = buildHostsExport(folders, hosts)
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  const date = new Date().toISOString().slice(0, 10)
  a.href = url
  a.download = `modernterminal-hosts-${date}.json`
  a.click()
  URL.revokeObjectURL(url)
}
