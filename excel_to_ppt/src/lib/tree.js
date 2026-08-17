const HEADER_WORDS = /维度|指标|口径|分类|类别|层级|一级|二级|三级|名称|name|category|dimension/i

export function trimMatrix(matrix) {
  const rows = matrix.map((row) => row.map(cleanCell))
  const nonEmptyRows = rows.map((row, index) => ({ row, index })).filter(({ row }) => row.some(Boolean))
  if (!nonEmptyRows.length) return []

  const top = nonEmptyRows[0].index
  const bottom = nonEmptyRows.at(-1).index
  let left = Infinity
  let right = -1
  rows.slice(top, bottom + 1).forEach((row) => {
    row.forEach((value, index) => {
      if (value) {
        left = Math.min(left, index)
        right = Math.max(right, index)
      }
    })
  })
  return rows.slice(top, bottom + 1).map((row) => row.slice(left, right + 1))
}

export function matrixToTree(input, rootLabel = '未命名主题') {
  const matrix = trimMatrix(input)
  if (!matrix.length) throw new Error('表格中没有可用数据')

  const firstDataIndex = detectHeader(matrix) ? 1 : 0
  const headers = firstDataIndex ? matrix[0] : matrix[0].map((_, i) => `层级 ${i + 1}`)
  const rows = matrix.slice(firstDataIndex).filter((row) => row.some(Boolean))
  if (!rows.length) throw new Error('表格只有表头，没有数据行')

  const activeColumns = headers
    .map((_, column) => column)
    .filter((column) => rows.some((row) => cleanCell(row[column])))
  if (!activeColumns.length) throw new Error('没有识别到层级列')

  const filled = Array(activeColumns.length).fill('')
  const paths = []
  rows.forEach((row) => {
    activeColumns.forEach((column, level) => {
      const value = cleanCell(row[column])
      if (value) {
        filled[level] = value
        filled.fill('', level + 1)
      }
    })
    const path = filled.filter(Boolean)
    if (path.length) paths.push(path)
  })

  const dedupedPaths = paths.filter((path, index) => {
    const key = path.join('\u0000')
    return paths.findIndex((item) => item.join('\u0000') === key) === index
  })
  const topLabels = [...new Set(dedupedPaths.map((path) => path[0]))]
  const virtualRoot = topLabels.length !== 1
  let sequence = 0
  const root = makeNode(virtualRoot ? rootLabel : topLabels[0], sequence++, 0, virtualRoot)

  dedupedPaths.forEach((path) => {
    const parts = virtualRoot ? path : path.slice(1)
    let parent = root
    parts.forEach((label) => {
      let child = parent.children.find((item) => item.label === label)
      if (!child) {
        child = makeNode(label, sequence++, parent.depth + 1, false)
        parent.children.push(child)
      }
      parent = child
    })
  })

  return {
    root,
    headers: activeColumns.map((index) => headers[index] || `层级 ${index + 1}`),
    rowCount: rows.length,
    nodeCount: sequence,
    maxDepth: getMaxDepth(root),
    virtualRoot,
  }
}

function detectHeader(matrix) {
  const first = matrix[0]
  const later = matrix.slice(1, Math.min(matrix.length, 8))
  const keywordHits = first.filter((value) => HEADER_WORDS.test(value)).length
  const density = first.filter(Boolean).length
  const laterBlankInFirstColumn = later.some((row) => !row[0] && row.slice(1).some(Boolean))
  return keywordHits > 0 || (density >= 2 && laterBlankInFirstColumn)
}

function makeNode(label, order, depth, virtual) {
  return { id: `n${order}`, label, order, depth, virtual, children: [] }
}

function cleanCell(value) {
  if (value === null || value === undefined) return ''
  return String(value).replace(/\s+/g, ' ').trim()
}

function getMaxDepth(node) {
  return node.children.length ? Math.max(...node.children.map(getMaxDepth)) : node.depth
}

export function flattenTree(root) {
  const nodes = []
  const visit = (node, parent = null) => {
    nodes.push({ ...node, parent })
    node.children.forEach((child) => visit(child, node))
  }
  visit(root)
  return nodes
}
