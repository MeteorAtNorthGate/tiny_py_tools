import { flattenTree } from './tree.js'

export const PALETTE = ['#2176ae', '#ef476f', '#06a6a6', '#f78c23', '#7957d5', '#2a9d46', '#9a5a46']

export function layoutTree(root) {
  const nodes = flattenTree(root)
  const maxDepth = Math.max(...nodes.map((node) => node.depth))
  const widths = Array(maxDepth + 1).fill(0)
  nodes.forEach((node) => {
    node.width = Math.max(150, Math.min(390, 52 + visualLength(node.label) * 14))
    node.height = node.label.length > 28 ? 64 : 52
    widths[node.depth] = Math.max(widths[node.depth], node.width)
  })

  const depthX = [54]
  for (let depth = 1; depth <= maxDepth; depth += 1) {
    depthX[depth] = depthX[depth - 1] + widths[depth - 1] + 150
  }

  let leafY = 46
  const position = (source) => {
    const node = nodes.find((item) => item.id === source.id)
    source.children.forEach(position)
    if (!source.children.length) {
      node.y = leafY
      leafY += 84
    } else {
      const childNodes = source.children.map((child) => nodes.find((item) => item.id === child.id))
      node.y = childNodes.reduce((sum, child) => sum + child.y, 0) / childNodes.length
    }
    node.x = depthX[node.depth]
  }
  position(root)

  const byId = Object.fromEntries(nodes.map((node) => [node.id, node]))
  nodes.forEach((node) => {
    let branch = node
    while (branch.parent && branch.parent.depth > 0) branch = byId[branch.parent.id]
    node.branchOrder = branch.depth === 0 ? 0 : branch.order
  })
  const edges = nodes.filter((node) => node.parent).map((node) => ({
    source: byId[node.parent.id],
    target: node,
  }))
  const width = Math.max(...nodes.map((node) => node.x + node.width)) + 64
  const height = Math.max(...nodes.map((node) => node.y + node.height)) + 46
  return { nodes, edges, width, height, maxDepth }
}

export function colorFor(node) {
  if (node.depth === 0) return '#20231f'
  return PALETTE[(node.branchOrder ?? node.order) % PALETTE.length]
}

function visualLength(text) {
  return [...text].reduce((length, char) => length + (/[^\u0000-\u00ff]/.test(char) ? 1 : 0.55), 0)
}
