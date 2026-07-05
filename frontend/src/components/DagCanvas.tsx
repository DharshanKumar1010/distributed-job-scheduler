import { useMemo } from 'react'
import type { JobStatus } from '../types'

export interface DagNode {
  id: string
  name: string
  status: JobStatus
}

// An edge always points from the job that must finish FIRST (from) to the
// job waiting on it (to) - visually rendered top-to-bottom.
export interface DagEdge {
  from: string
  to: string
}

interface DagCanvasProps {
  nodes: DagNode[]
  edges: DagEdge[]
  selectedId?: string | null
  onNodeClick?: (id: string) => void
  liveStatuses?: Record<string, JobStatus>
}

const NODE_WIDTH = 160
const NODE_HEIGHT = 60
const LEVEL_SPACING_X = 200
const ROW_SPACING_Y = 80
const MARGIN = 40

const STATUS_FILL: Record<string, string> = {
  queued: 'var(--border)',
  scheduled: 'var(--border)',
  claimed: 'rgba(245, 158, 11, 0.15)',
  running: 'var(--accent-glow)',
  completed: 'rgba(16, 185, 129, 0.1)',
  blocked: 'rgba(100, 116, 139, 0.1)',
  failed: 'rgba(239, 68, 68, 0.1)',
  dead: 'rgba(239, 68, 68, 0.1)',
  cancelled: 'rgba(100, 116, 139, 0.1)',
}

const STATUS_STROKE: Record<string, string> = {
  queued: '#94A3B8',
  scheduled: '#94A3B8',
  claimed: '#F59E0B',
  running: '#F59E0B',
  completed: '#10B981',
  blocked: '#64748B',
  failed: '#EF4444',
  dead: '#EF4444',
  cancelled: '#64748B',
}

function truncate(name: string, max = 18): string {
  return name.length > max ? `${name.slice(0, max - 1)}…` : name
}

interface LaidOutNode extends DagNode {
  x: number
  y: number
}

function layoutNodes(nodes: DagNode[], edges: DagEdge[]): Map<string, LaidOutNode> {
  const childrenOf = new Map<string, string[]>()
  const inDegree = new Map<string, number>()
  nodes.forEach((n) => {
    childrenOf.set(n.id, [])
    inDegree.set(n.id, 0)
  })
  edges.forEach((e) => {
    if (!childrenOf.has(e.from) || !inDegree.has(e.to)) return
    childrenOf.get(e.from)!.push(e.to)
    inDegree.set(e.to, (inDegree.get(e.to) ?? 0) + 1)
  })

  const level = new Map<string, number>()
  const remaining = new Map(inDegree)
  const queue = nodes.filter((n) => (inDegree.get(n.id) ?? 0) === 0).map((n) => n.id)
  queue.forEach((id) => level.set(id, 0))

  for (let i = 0; i < queue.length; i++) {
    const id = queue[i]
    const currentLevel = level.get(id) ?? 0
    for (const child of childrenOf.get(id) ?? []) {
      level.set(child, Math.max(level.get(child) ?? 0, currentLevel + 1))
      remaining.set(child, (remaining.get(child) ?? 0) - 1)
      if (remaining.get(child) === 0) queue.push(child)
    }
  }
  // Cycles/orphans (shouldn't happen - the backend rejects cycles) still get a level.
  nodes.forEach((n) => {
    if (!level.has(n.id)) level.set(n.id, 0)
  })

  const byLevel = new Map<number, DagNode[]>()
  nodes.forEach((n) => {
    const lvl = level.get(n.id) ?? 0
    if (!byLevel.has(lvl)) byLevel.set(lvl, [])
    byLevel.get(lvl)!.push(n)
  })
  byLevel.forEach((group) => group.sort((a, b) => a.name.localeCompare(b.name)))

  const result = new Map<string, LaidOutNode>()
  byLevel.forEach((group, lvl) => {
    group.forEach((n, idx) => {
      result.set(n.id, {
        ...n,
        x: MARGIN + lvl * LEVEL_SPACING_X,
        y: MARGIN + idx * ROW_SPACING_Y,
      })
    })
  })
  return result
}

function EdgePath({
  source,
  target,
  animated,
}: {
  source: LaidOutNode
  target: LaidOutNode
  animated: boolean
}) {
  const x1 = source.x + NODE_WIDTH / 2
  const y1 = source.y + NODE_HEIGHT
  const x2 = target.x + NODE_WIDTH / 2
  const y2 = target.y
  const dy = (y2 - y1) / 2
  const path = `M ${x1} ${y1} C ${x1} ${y1 + dy}, ${x2} ${y2 - dy}, ${x2} ${y2}`
  const stroke = source.status === 'completed' ? 'var(--accent)' : 'var(--border)'

  return (
    <path
      d={path}
      fill="none"
      stroke={stroke}
      strokeWidth={1.5}
      strokeDasharray={animated ? '6 4' : undefined}
    >
      {animated && (
        <animate
          attributeName="stroke-dashoffset"
          from="20"
          to="0"
          dur="0.6s"
          repeatCount="indefinite"
        />
      )}
    </path>
  )
}

export function DagCanvas({ nodes, edges, selectedId, onNodeClick, liveStatuses }: DagCanvasProps) {
  const effectiveNodes = useMemo(
    () => nodes.map((n) => ({ ...n, status: liveStatuses?.[n.id] ?? n.status })),
    [nodes, liveStatuses],
  )
  const laidOut = useMemo(() => layoutNodes(effectiveNodes, edges), [effectiveNodes, edges])

  const { width, height } = useMemo(() => {
    let maxX = 0
    let maxY = 0
    laidOut.forEach((n) => {
      maxX = Math.max(maxX, n.x + NODE_WIDTH)
      maxY = Math.max(maxY, n.y + NODE_HEIGHT)
    })
    return { width: maxX + MARGIN, height: maxY + MARGIN }
  }, [laidOut])

  if (nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-secondary">
        No jobs to display
      </div>
    )
  }

  return (
    <svg
      viewBox={`0 0 ${Math.max(width, NODE_WIDTH + 2 * MARGIN)} ${Math.max(height, NODE_HEIGHT + 2 * MARGIN)}`}
      width="100%"
      className="min-h-[280px]"
    >
      <g>
        {edges.map((edge) => {
          const source = laidOut.get(edge.from)
          const target = laidOut.get(edge.to)
          if (!source || !target) return null
          const animated = source.status === 'completed' && target.status === 'running'
          return (
            <EdgePath key={`${edge.from}->${edge.to}`} source={source} target={target} animated={animated} />
          )
        })}
      </g>
      <g>
        {Array.from(laidOut.values()).map((node) => {
          const isSelected = node.id === selectedId
          const fill = STATUS_FILL[node.status] ?? STATUS_FILL.queued
          const stroke = STATUS_STROKE[node.status] ?? STATUS_STROKE.queued
          return (
            <g
              key={node.id}
              transform={`translate(${node.x}, ${node.y})`}
              onClick={() => onNodeClick?.(node.id)}
              style={{ cursor: onNodeClick ? 'pointer' : 'default' }}
            >
              <rect
                width={NODE_WIDTH}
                height={NODE_HEIGHT}
                rx={10}
                fill={fill}
                stroke={isSelected ? 'var(--accent)' : stroke}
                strokeWidth={isSelected ? 2 : 1}
              />
              <text
                x={12}
                y={24}
                fontSize={12}
                fontFamily="var(--font-display, sans-serif)"
                fill="var(--text-primary)"
              >
                {truncate(node.name)}
              </text>
              <rect x={12} y={34} width={64} height={16} rx={8} fill={stroke} opacity={0.18} />
              <text
                x={20}
                y={46}
                fontSize={9}
                fill={stroke}
                letterSpacing={0.5}
                style={{ textTransform: 'uppercase' }}
              >
                {node.status}
              </text>
            </g>
          )
        })}
      </g>
    </svg>
  )
}
