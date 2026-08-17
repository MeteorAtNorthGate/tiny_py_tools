import pptxgen from 'pptxgenjs'
import { colorFor, PALETTE, RELATION_GAP } from './layout.js'

const PX_PER_INCH = 96
const MAX_SLIDE_INCH = 56
const MARGIN_INCH = 0.45

export function treeToMermaid(root) {
  const lines = [
    '%%{init: {"theme":"base","themeVariables":{"background":"#FBFBF8","primaryTextColor":"#20231F","textColor":"#20231F","edgeLabelBackground":"#FBFBF8","fontFamily":"Microsoft YaHei, sans-serif","lineColor":"#8A8F86"},"themeCSS":".edgeLabel,.edgeLabel p,.edgeLabel div,.edgeLabel span,.edgeLabel foreignObject{background:transparent!important;color:#20231F!important}.edgeLabel foreignObject{transform-box:fill-box!important;transform:translateY(calc(-50% - 4px))!important;overflow:visible!important}.edgeLabel text,.edgeLabel tspan,.edgeLabel .label{fill:#20231F!important;color:#20231F!important}.edgeLabel rect{fill:none!important;stroke:none!important}","flowchart":{"curve":"basis","htmlLabels":true}}}%%',
    'flowchart LR',
    '  origin(( ))',
  ]
  const pointStyles = []
  const linkStyles = []
  let linkIndex = 0

  const declarePoints = (node, branchIndex = null) => {
    lines.push(`  ${node.id}(( ))`)
    if (node === root) {
      pointStyles.push(`  style ${node.id} fill:none,stroke:#20231F,stroke-width:2px;`)
    } else {
      const color = PALETTE[branchIndex % PALETTE.length]
      pointStyles.push(`  style ${node.id} fill:none,stroke:${color},stroke-width:2px;`)
    }
    node.children.forEach((child, index) => {
      const childBranch = node === root ? index : branchIndex
      declarePoints(child, childBranch)
    })
  }
  declarePoints(root)

  lines.push(`  origin ---|${escapeMermaid(root.label)}| ${root.id}`)
  linkStyles.push('  linkStyle 0 stroke:#20231F,stroke-width:2px;')
  linkIndex += 1

  const walk = (node, branchIndex = null) => {
    node.children.forEach((child) => {
      const childBranch = node === root ? node.children.indexOf(child) : branchIndex
      lines.push(`  ${node.id} ---|${escapeMermaid(child.label)}| ${child.id}`)
      linkStyles.push(`  linkStyle ${linkIndex} stroke:${PALETTE[childBranch % PALETTE.length]},stroke-width:2px;`)
      linkIndex += 1
      walk(child, childBranch)
    })
  }
  walk(root)

  lines.push('  style origin fill:none,stroke:none;')
  lines.push(...pointStyles)
  lines.push(...linkStyles)
  return lines.join('\n')
}

export function downloadMermaid(root, baseName) {
  downloadBlob(new Blob([treeToMermaid(root)], { type: 'text/plain;charset=utf-8' }), `${baseName}.mmd`)
}

export async function exportPptx(layout, baseName) {
  const naturalWidth = layout.width / PX_PER_INCH + MARGIN_INCH * 2
  const naturalHeight = layout.height / PX_PER_INCH + MARGIN_INCH * 2
  const shrink = Math.min(1, MAX_SLIDE_INCH / naturalWidth, MAX_SLIDE_INCH / naturalHeight)
  const slideWidth = Math.max(1, naturalWidth * shrink)
  const slideHeight = Math.max(1, naturalHeight * shrink)
  const unit = shrink / PX_PER_INCH

  const pptx = new pptxgen()
  pptx.author = '表格成树'
  pptx.subject = '由 Excel / CSV 生成的可编辑树状图'
  pptx.title = baseName
  pptx.company = ''
  pptx.lang = 'zh-CN'
  pptx.defineLayout({ name: 'TREE_CANVAS', width: slideWidth, height: slideHeight })
  pptx.layout = 'TREE_CANVAS'
  pptx.theme = {
    headFontFace: 'Microsoft YaHei',
    bodyFontFace: 'Microsoft YaHei',
    lang: 'zh-CN',
  }
  const slide = pptx.addSlide()
  slide.background = { color: 'FBFBF8' }

  // A single native brace expresses each parent-child group. We intentionally
  // avoid composed line connectors: upward lines create negative OOXML extents
  // that some PowerPoint versions repair or discard.
  const nodeById = Object.fromEntries(layout.nodes.map((node) => [node.id, node]))
  layout.nodes.filter((node) => node.children.length > 1).forEach((node) => {
    const childNodes = node.children.map((child) => nodeById[child.id])
    const top = Math.min(...childNodes.map((child) => child.y))
    const bottom = Math.max(...childNodes.map((child) => child.y + child.height))
    const braceX = node.x + node.width + RELATION_GAP.parentToBrace
    slide.addShape(pptx.ShapeType.leftBrace, {
      x: MARGIN_INCH + braceX * unit,
      y: MARGIN_INCH + top * unit,
      w: Math.max(0.08, RELATION_GAP.braceWidth * unit),
      h: Math.max(0.12, (bottom - top) * unit),
      fill: { color: 'FFFFFF', transparency: 100 },
      line: { color: colorFor(node).slice(1), width: Math.max(0.5, 1.1 * shrink) },
    })
  })

  layout.nodes.filter((node) => node.children.length === 1).forEach((node) => {
    const child = nodeById[node.children[0].id]
    const x1 = MARGIN_INCH + (node.x + node.width) * unit
    const x2 = MARGIN_INCH + child.x * unit
    const y = MARGIN_INCH + (node.y + node.height / 2) * unit
    slide.addShape(pptx.ShapeType.line, {
      x: x1,
      y,
      w: x2 - x1,
      h: 0,
      line: {
        color: colorFor(node).slice(1),
        width: Math.max(0.5, 1.1 * shrink),
        beginArrowType: 'none',
        endArrowType: 'none',
      },
    })
  })

  layout.nodes.forEach((node) => {
    const color = colorFor(node).slice(1)
    slide.addText(node.label, {
      x: MARGIN_INCH + node.x * unit,
      y: MARGIN_INCH + node.y * unit,
      w: node.width * unit,
      h: node.height * unit,
      shape: pptx.ShapeType.roundRect,
      rectRadius: 0.08,
      fill: { color: node.depth === 0 ? '20231F' : 'FFFFFF' },
      line: { color, width: Math.max(0.7, 1.5 * shrink) },
      color: node.depth === 0 ? 'FFFFFF' : '20231F',
      fontFace: 'Microsoft YaHei',
      fontSize: Math.max(7, 14 * shrink),
      bold: node.depth <= 1,
      align: 'center',
      valign: 'mid',
      margin: Math.max(0.025, 0.07 * shrink),
      breakLine: false,
      fit: 'shrink',
    })
  })

  await pptx.writeFile({ fileName: `${baseName}.pptx` })
}

function escapeMermaid(value) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/\|/g, '&#124;')
    .replace(/[\r\n]+/g, ' ')
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
