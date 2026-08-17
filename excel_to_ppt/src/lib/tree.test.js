import { describe, expect, it } from 'vitest'
import { matrixToTree, trimMatrix } from './tree'

describe('table normalization', () => {
  it('trims data starting outside A1 and fills missing parents', () => {
    const matrix = [
      ['', '', '', ''],
      ['', '一级', '二级', '三级'],
      ['', '甲', '甲一', '叶一'],
      ['', '', '', '叶二'],
      ['', '乙', '乙一', '叶三'],
    ]
    expect(trimMatrix(matrix)[0]).toEqual(['一级', '二级', '三级'])
    const result = matrixToTree(matrix, '自动根')
    expect(result.virtualRoot).toBe(true)
    expect(result.root.label).toBe('自动根')
    expect(result.root.children.map((node) => node.label)).toEqual(['甲', '乙'])
    expect(result.root.children[0].children[0].children).toHaveLength(2)
  })

  it('does not add a virtual root when data has one root', () => {
    const result = matrixToTree([
      ['层级1', '层级2'],
      ['唯一根', '节点 A'],
      ['', '节点 B'],
    ], '不会使用')
    expect(result.virtualRoot).toBe(false)
    expect(result.root.label).toBe('唯一根')
    expect(result.root.children).toHaveLength(2)
  })
})
