import pptxgen from 'pptxgenjs'
import { colorFor } from './layout.js'

const PX_PER_INCH = 96
const MAX_SLIDE_INCH = 56
const MARGIN_INCH = 0.45

export function treeToMermaid(root) {
  const lines = ['flowchart LR']
  const walk = (node) => {
    lines.push(`  ${node.id}["${escapeMermaid(node.label)}"]`)
    node.children.forEach((child) => {
      lines.push(`  ${node.id} --> ${child.id}`)
      walk(child)
    })
  }
  walk(root)
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
  layout.nodes.filter((node) => node.children.length > 0).forEach((node) => {
    const childNodes = node.children.map((child) => nodeById[child.id])
    const top = Math.min(...childNodes.map((child) => child.y))
    const bottom = Math.max(...childNodes.map((child) => child.y + child.height))
    const braceX = Math.min(...childNodes.map((child) => child.x)) - 62
    slide.addShape(pptx.ShapeType.leftBrace, {
      x: MARGIN_INCH + braceX * unit,
      y: MARGIN_INCH + top * unit,
      w: Math.max(0.08, 26 * unit),
      h: Math.max(0.12, (bottom - top) * unit),
      fill: { color: 'FFFFFF', transparency: 100 },
      line: { color: colorFor(node).slice(1), width: Math.max(0.5, 1.1 * shrink) },
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
  return value.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/[\r\n]+/g, ' ')
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
