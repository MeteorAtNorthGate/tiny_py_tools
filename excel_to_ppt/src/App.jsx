import { useMemo, useRef, useState } from 'react'
import { Download, FileJson2, FileSpreadsheet, GitBranch, LoaderCircle, Upload, X } from 'lucide-react'
import TreePreview from './components/TreePreview'
import { readTableFile } from './lib/file'
import { layoutTree } from './lib/layout'
import { downloadMermaid, exportPptx } from './lib/export'
import { matrixToTree } from './lib/tree'

const EXAMPLE_MATRIX = [
  ['对比维度', '可量化指标', '指标口径 / 采集建议'],
  ['战略与方向评估', '业务聚焦程度', '主营产品收入占比'],
  ['', '', '目标达成率'],
  ['', '决策与授权', '平均决策周期'],
  ['组织与人才管理', '团队稳定性', '核心高管留存率'],
  ['', '人才建设', '内部晋升率'],
  ['研发与产品管理', '技术研发效能', '核心系统可用性'],
]

export default function App() {
  const fileInput = useRef(null)
  const [rootName, setRootName] = useState('企业指标体系')
  const [fileName, setFileName] = useState('示例数据')
  const [source, setSource] = useState(() => buildSource(EXAMPLE_MATRIX, '企业指标体系'))
  const [busy, setBusy] = useState('')
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState('')

  const layout = useMemo(() => layoutTree(source.tree.root), [source])

  async function importFile(file) {
    if (!file) return
    setBusy('读取表格')
    setError('')
    try {
      const result = await readTableFile(file)
      const next = buildSource(result.matrix, rootName)
      setSource({ ...next, sheetName: result.sheetName, sheetCount: result.sheetCount })
      setFileName(stripExtension(file.name))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '文件读取失败')
    } finally {
      setBusy('')
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  function updateRoot(value) {
    setRootName(value)
    if (source.tree.virtualRoot) {
      const root = { ...source.tree.root, label: value || '未命名主题' }
      setSource({ ...source, tree: { ...source.tree, root } })
    }
  }

  async function handlePptx() {
    setBusy('生成 PPTX')
    setError('')
    try {
      await exportPptx(layout, safeFilename(fileName || rootName))
    } catch (reason) {
      console.error(reason)
      setError(`PPTX 生成失败：${reason instanceof Error ? reason.message : '未知错误'}`)
    } finally {
      setBusy('')
    }
  }

  return (
    <main className="min-h-screen bg-[#f2f2ed] px-4 py-5 text-[#20231f] sm:px-7 lg:px-10">
      <header className="mx-auto flex max-w-[1800px] items-center justify-between border-b border-[#ced0c8] pb-5">
        <div className="flex items-center gap-3">
          <div className="grid size-11 place-items-center rounded-2xl bg-[#20231f] text-white shadow-sm">
            <GitBranch size={22} />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-[-0.03em]">表格成树</h1>
            <p className="text-xs text-[#6f736b]">Excel / CSV → Mermaid + 可编辑 PPTX</p>
          </div>
        </div>
        <div className="hidden rounded-full border border-[#d4d6cf] bg-white/70 px-4 py-2 text-xs text-[#676b63] sm:block">
          文件仅在浏览器本地处理
        </div>
      </header>

      <div className="mx-auto mt-7 grid max-w-[1800px] gap-7 xl:grid-cols-[340px_minmax(0,1fr)]">
        <aside className="space-y-4">
          <section className="rounded-[26px] bg-[#20231f] p-5 text-white shadow-[0_18px_45px_rgba(28,31,27,0.16)]">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#aeb3a8]">01 / 导入</p>
            <button
              type="button"
              onClick={() => fileInput.current?.click()}
              onDragEnter={(event) => { event.preventDefault(); setDragging(true) }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault()
                setDragging(false)
                importFile(event.dataTransfer.files[0])
              }}
              className={`mt-4 flex w-full flex-col items-center rounded-2xl border border-dashed px-4 py-8 transition ${dragging ? 'border-[#e9ff70] bg-white/10' : 'border-[#646960] bg-white/[0.04] hover:bg-white/[0.08]'}`}
            >
              <Upload className="mb-3 text-[#e9ff70]" size={25} />
              <span className="text-sm font-semibold">拖入或选择表格</span>
              <span className="mt-1 text-xs text-[#aeb3a8]">.xlsx / .csv</span>
            </button>
            <input
              ref={fileInput}
              type="file"
              accept=".xlsx,.csv"
              className="hidden"
              onChange={(event) => importFile(event.target.files?.[0])}
            />
          </section>

          <section className="rounded-[26px] border border-[#d8d9d2] bg-[#fbfbf8] p-5">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#858a80]">02 / 设置</p>
            <label className="mt-4 block text-xs font-semibold text-[#62675e]" htmlFor="root-name">缺失根节点时的名称</label>
            <input
              id="root-name"
              value={rootName}
              onChange={(event) => updateRoot(event.target.value)}
              className="mt-2 w-full rounded-xl border border-[#d2d5cc] bg-white px-3.5 py-2.5 text-sm outline-none transition focus:border-[#20231f]"
            />
            <div className="mt-5 grid grid-cols-2 gap-2">
              <Stat value={source.tree.rowCount} label="数据行" />
              <Stat value={source.tree.nodeCount} label="节点" />
              <Stat value={source.tree.maxDepth + 1} label="层级" />
              <Stat value={source.tree.virtualRoot ? '已补齐' : '原生'} label="根节点" />
            </div>
            <div className="mt-4 rounded-xl bg-[#eeefe9] px-3.5 py-3 text-xs leading-5 text-[#63685e]">
              已自动忽略表格四周空白，识别任意起始单元格，并展开合并单元格与补齐父级。
            </div>
          </section>

          <section className="rounded-[26px] border border-[#d8d9d2] bg-[#fbfbf8] p-5">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#858a80]">03 / 导出</p>
            <div className="mt-4 space-y-2.5">
              <button
                type="button"
                disabled={Boolean(busy)}
                onClick={handlePptx}
                className="flex w-full items-center justify-between rounded-xl bg-[#e9ff70] px-4 py-3 text-sm font-bold text-[#20231f] transition hover:bg-[#ddf65b] disabled:opacity-50"
              >
                <span className="flex items-center gap-2"><FileSpreadsheet size={17} />可编辑 PPTX</span>
                <Download size={16} />
              </button>
              <button
                type="button"
                disabled={Boolean(busy)}
                onClick={() => downloadMermaid(source.tree.root, safeFilename(fileName || rootName))}
                className="flex w-full items-center justify-between rounded-xl border border-[#cfd2c8] bg-white px-4 py-3 text-sm font-semibold transition hover:border-[#20231f] disabled:opacity-50"
              >
                <span className="flex items-center gap-2"><FileJson2 size={17} />Mermaid .mmd</span>
                <Download size={16} />
              </button>
            </div>
          </section>
        </aside>

        <section className="min-w-0">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3 px-1">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#858a80]">实时预览</p>
              <h2 className="mt-1 text-2xl font-bold tracking-[-0.035em]">{source.tree.root.label}</h2>
              <p className="mt-1 text-xs text-[#777c72]">
                {fileName} · {source.sheetName || '示例'} · 画布 {layout.width} × {layout.height}
              </p>
            </div>
            <div className="rounded-full bg-white px-3.5 py-2 text-xs text-[#656a61] shadow-sm">拖动滚动条查看完整树</div>
          </div>
          {error && (
            <div className="mb-4 flex items-center justify-between rounded-2xl border border-[#edb9b9] bg-[#fff1f1] px-4 py-3 text-sm text-[#9d3030]">
              {error}<button type="button" onClick={() => setError('')}><X size={17} /></button>
            </div>
          )}
          <TreePreview layout={layout} />
        </section>
      </div>

      {busy && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-[#20231f]/35 backdrop-blur-[2px]">
          <div className="flex items-center gap-3 rounded-2xl bg-white px-5 py-4 text-sm font-semibold shadow-xl">
            <LoaderCircle className="animate-spin" size={19} />{busy}…
          </div>
        </div>
      )}
    </main>
  )
}

function Stat({ value, label }) {
  return (
    <div className="rounded-xl border border-[#e0e1dc] bg-white px-3 py-2.5">
      <div className="text-base font-bold">{value}</div>
      <div className="text-[10px] text-[#858a80]">{label}</div>
    </div>
  )
}

function buildSource(matrix, rootName) {
  return { tree: matrixToTree(matrix, rootName), sheetName: '示例', sheetCount: 1 }
}

function stripExtension(name) {
  return name.replace(/\.[^.]+$/, '')
}

function safeFilename(name) {
  return (name || '树状图').replace(/[\\/:*?"<>|]/g, '_').trim()
}
