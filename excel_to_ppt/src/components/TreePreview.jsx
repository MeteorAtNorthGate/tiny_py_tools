import { colorFor, RELATION_GAP } from '../lib/layout'

export default function TreePreview({ layout }) {
  return (
    <div className="canvas-grid thin-scrollbar h-full min-h-[520px] overflow-auto rounded-[28px] border border-[#d7d8d1] shadow-[0_18px_50px_rgba(33,38,31,0.08)]">
      <svg
        width={layout.width}
        height={layout.height}
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        role="img"
        aria-label="树状图预览"
      >
        <g fill="none" strokeLinecap="round" strokeLinejoin="round">
          {layout.nodes.filter((node) => node.children.length > 1).map((node) => {
            const children = node.children.map((child) => layout.nodes.find((item) => item.id === child.id))
            const top = Math.min(...children.map((child) => child.y))
            const bottom = Math.max(...children.map((child) => child.y + child.height))
            const x = node.x + node.width + RELATION_GAP.parentToBrace
            const width = RELATION_GAP.braceWidth
            const height = bottom - top
            return (
              <path
                key={`brace-${node.id}`}
                d={bracePath(x, top, width, height)}
                stroke={colorFor(node)}
                strokeWidth="2"
                opacity="0.72"
              />
            )
          })}
          {layout.nodes.filter((node) => node.children.length === 1).map((node) => {
            const child = layout.nodes.find((item) => item.id === node.children[0].id)
            const y = node.y + node.height / 2
            return (
              <line
                key={`line-${node.id}`}
                x1={node.x + node.width}
                y1={y}
                x2={child.x}
                y2={y}
                stroke={colorFor(node)}
                strokeWidth="2"
                opacity="0.72"
              />
            )
          })}
        </g>
        {layout.nodes.map((node) => {
          const color = colorFor(node)
          return (
            <g key={node.id} transform={`translate(${node.x} ${node.y})`}>
              <rect
                width={node.width}
                height={node.height}
                rx="15"
                fill={node.depth === 0 ? '#20231f' : '#fff'}
                stroke={color}
                strokeWidth={node.depth === 0 ? 0 : 2}
              />
              <foreignObject x="10" y="4" width={node.width - 20} height={node.height - 8}>
                <div
                  xmlns="http://www.w3.org/1999/xhtml"
                  className={`flex h-full items-center justify-center text-center text-[14px] leading-[1.3] ${node.depth <= 1 ? 'font-semibold' : 'font-medium'}`}
                  style={{ color: node.depth === 0 ? '#fff' : '#20231f' }}
                >
                  {node.label}
                </div>
              </foreignObject>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function bracePath(x, y, width, height) {
  const quarter = height * 0.22
  const middle = height * 0.5
  return [
    `M ${x + width} ${y}`,
    `C ${x + width * 0.28} ${y} ${x + width * 0.28} ${y + quarter * 0.45} ${x + width * 0.28} ${y + quarter}`,
    `L ${x + width * 0.28} ${y + middle - quarter * 0.42}`,
    `C ${x + width * 0.28} ${y + middle - quarter * 0.12} ${x} ${y + middle - quarter * 0.08} ${x} ${y + middle}`,
    `C ${x} ${y + middle + quarter * 0.08} ${x + width * 0.28} ${y + middle + quarter * 0.12} ${x + width * 0.28} ${y + middle + quarter * 0.42}`,
    `L ${x + width * 0.28} ${y + height - quarter}`,
    `C ${x + width * 0.28} ${y + height - quarter * 0.45} ${x + width * 0.28} ${y + height} ${x + width} ${y + height}`,
  ].join(' ')
}
