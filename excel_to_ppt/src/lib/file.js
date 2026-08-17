import * as XLSX from 'xlsx'
import Papa from 'papaparse'

export async function readTableFile(file) {
  const extension = file.name.split('.').pop()?.toLowerCase()
  if (extension === 'csv') return readCsv(file)
  if (extension === 'xlsx') return readWorkbook(file)
  throw new Error('仅支持 .xlsx 或 .csv 文件')
}

async function readWorkbook(file) {
  const workbook = XLSX.read(await file.arrayBuffer(), { type: 'array', cellDates: true })
  const sheetName = workbook.SheetNames[0]
  if (!sheetName) throw new Error('工作簿中没有工作表')
  const sheet = workbook.Sheets[sheetName]
  expandMergedCells(sheet)
  const matrix = XLSX.utils.sheet_to_json(sheet, {
    header: 1,
    defval: '',
    raw: false,
    blankrows: false,
  })
  return { matrix, sheetName, sheetCount: workbook.SheetNames.length }
}

function expandMergedCells(sheet) {
  for (const range of sheet['!merges'] || []) {
    const source = sheet[XLSX.utils.encode_cell(range.s)]
    if (!source) continue
    for (let row = range.s.r; row <= range.e.r; row += 1) {
      for (let column = range.s.c; column <= range.e.c; column += 1) {
        const address = XLSX.utils.encode_cell({ r: row, c: column })
        if (!sheet[address]) sheet[address] = { ...source }
      }
    }
  }
}

function readCsv(file) {
  return new Promise((resolve, reject) => {
    Papa.parse(file, {
      skipEmptyLines: 'greedy',
      complete: ({ data, errors }) => {
        const fatal = errors.find((error) => error.type === 'Quotes')
        if (fatal) reject(new Error(`CSV 解析失败：${fatal.message}`))
        else resolve({ matrix: data, sheetName: file.name, sheetCount: 1 })
      },
      error: reject,
    })
  })
}
