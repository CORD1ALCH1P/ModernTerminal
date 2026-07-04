import type { Folder, Host } from '../api/types'

export interface FolderTreeNode {
  folder: Folder
  children: FolderTreeNode[]
  hosts: Host[]
}

export function buildTree(folders: Folder[], hosts: Host[]): { roots: FolderTreeNode[]; rootHosts: Host[] } {
  const nodeMap = new Map<number, FolderTreeNode>()
  for (const folder of folders) {
    nodeMap.set(folder.id, { folder, children: [], hosts: [] })
  }

  const roots: FolderTreeNode[] = []
  for (const folder of [...folders].sort((a, b) => a.sort_order - b.sort_order)) {
    const node = nodeMap.get(folder.id)
    if (!node) continue
    const parent = folder.parent_id !== null ? nodeMap.get(folder.parent_id) : undefined
    if (parent) {
      parent.children.push(node)
    } else {
      roots.push(node)
    }
  }

  const rootHosts: Host[] = []
  for (const host of [...hosts].sort((a, b) => a.sort_order - b.sort_order)) {
    const parent = host.folder_id !== null ? nodeMap.get(host.folder_id) : undefined
    if (parent) {
      parent.hosts.push(host)
    } else {
      rootHosts.push(host)
    }
  }

  return { roots, rootHosts }
}
