import { flattenTree } from './tree.js'

export const HSL_THEME = Object.freeze({
  root: { h: 105, s: 6, l: 13 },
  firstLevel: {
    hueStart: 205,
    hueSpan: 300,
    saturation: 68,
    lightness: 43,
  },
  secondLevel: {
    saturationHigh: 74,
    saturationLow: 62,
  },
  deeperLevels: {
    lightnessStep: 6,
    siblingVariation: 6,
    minLightness: 34,
    maxLightness: 64,
  },
})
export const RELATION_GAP = {
  parentToBrace: 20,
  braceWidth: 26,
  braceToChildren: 20,
  singleChildLine: 66,
}

export function layoutTree(root) {
  const nodes = flattenTree(root)
  const maxDepth = Math.max(...nodes.map((node) => node.depth))
  nodes.forEach((node) => {
    node.width = Math.max(150, Math.min(390, 52 + visualLength(node.label) * 14))
    node.height = node.label.length > 28 ? 64 : 52
  })

  let leafY = 46
  const position = (source, x = 54) => {
    const node = nodes.find((item) => item.id === source.id)
    node.x = x
    const relationWidth = source.children.length === 1
      ? RELATION_GAP.singleChildLine
      : RELATION_GAP.parentToBrace + RELATION_GAP.braceWidth + RELATION_GAP.braceToChildren
    source.children.forEach((child) => position(child, x + node.width + relationWidth))
    if (!source.children.length) {
      node.y = leafY
      leafY += 84
    } else {
      const childNodes = source.children.map((child) => nodes.find((item) => item.id === child.id))
      const childCenter = childNodes.reduce((sum, child) => sum + child.y + child.height / 2, 0) / childNodes.length
      node.y = childCenter - node.height / 2
    }
  }
  position(root)

  const byId = Object.fromEntries(nodes.map((node) => [node.id, node]))
  const colors = createTreeColorMap(root)
  nodes.forEach((node) => {
    node.color = colors.get(node.id)
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
  return node.color?.hex || hslToHex(HSL_THEME.root)
}

export function createTreeColorMap(root) {
  const colors = new Map()
  colors.set(root.id, makeColor(HSL_THEME.root))

  root.children.forEach((firstLevelNode, index) => {
    const firstLevel = {
      h: distributeHue(index, root.children.length),
      s: HSL_THEME.firstLevel.saturation,
      l: HSL_THEME.firstLevel.lightness,
    }
    assignColor(firstLevelNode, firstLevel)
  })

  return colors

  function assignColor(node, hsl) {
    colors.set(node.id, makeColor(hsl))
    node.children.forEach((child, index) => {
      let childHsl
      if (child.depth === 2) {
        childHsl = {
          ...hsl,
          s: spread(
            index,
            node.children.length,
            HSL_THEME.secondLevel.saturationHigh,
            HSL_THEME.secondLevel.saturationLow,
          ),
        }
      } else {
        const variation = spread(
          index,
          node.children.length,
          HSL_THEME.deeperLevels.siblingVariation / 2,
          -HSL_THEME.deeperLevels.siblingVariation / 2,
        )
        childHsl = {
          ...hsl,
          l: clamp(
            hsl.l + HSL_THEME.deeperLevels.lightnessStep + variation,
            HSL_THEME.deeperLevels.minLightness,
            HSL_THEME.deeperLevels.maxLightness,
          ),
        }
      }
      assignColor(child, childHsl)
    })
  }
}

export function hslToHex({ h, s, l }) {
  const saturation = s / 100
  const lightness = l / 100
  const chroma = (1 - Math.abs(2 * lightness - 1)) * saturation
  const segment = (((h % 360) + 360) % 360) / 60
  const secondary = chroma * (1 - Math.abs((segment % 2) - 1))
  const offset = lightness - chroma / 2
  let rgb

  if (segment < 1) rgb = [chroma, secondary, 0]
  else if (segment < 2) rgb = [secondary, chroma, 0]
  else if (segment < 3) rgb = [0, chroma, secondary]
  else if (segment < 4) rgb = [0, secondary, chroma]
  else if (segment < 5) rgb = [secondary, 0, chroma]
  else rgb = [chroma, 0, secondary]

  return `#${rgb.map((channel) => Math.round((channel + offset) * 255).toString(16).padStart(2, '0')).join('')}`
}

function visualLength(text) {
  return [...text].reduce((length, char) => length + (/[^\u0000-\u00ff]/.test(char) ? 1 : 0.55), 0)
}

function distributeHue(index, count) {
  if (count <= 1) return HSL_THEME.firstLevel.hueStart
  return (HSL_THEME.firstLevel.hueStart + HSL_THEME.firstLevel.hueSpan * index / (count - 1)) % 360
}

function spread(index, count, start, end) {
  if (count <= 1) return (start + end) / 2
  return start + (end - start) * index / (count - 1)
}

function makeColor(hsl) {
  const normalized = {
    h: Math.round(hsl.h * 10) / 10,
    s: Math.round(hsl.s * 10) / 10,
    l: Math.round(hsl.l * 10) / 10,
  }
  return { ...normalized, hex: hslToHex(normalized) }
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value))
}
