import { Fragment, useState, type ReactNode } from 'react'

function colorizeJson(value: unknown, indent: number): ReactNode {
  const pad = '  '.repeat(indent)
  const childPad = '  '.repeat(indent + 1)

  if (value === null) return <span style={{ color: 'var(--text-mono)' }}>null</span>
  if (typeof value === 'boolean' || typeof value === 'number') {
    return <span style={{ color: 'var(--accent)' }}>{String(value)}</span>
  }
  if (typeof value === 'string') {
    return <span style={{ color: 'var(--success)' }}>&quot;{value}&quot;</span>
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return <span>[]</span>
    return (
      <>
        {'[\n'}
        {value.map((item, i) => (
          <Fragment key={i}>
            {childPad}
            {colorizeJson(item, indent + 1)}
            {i < value.length - 1 ? ',' : ''}
            {'\n'}
          </Fragment>
        ))}
        {pad}
        {']'}
      </>
    )
  }

  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
    if (entries.length === 0) return <span>{'{}'}</span>
    return (
      <>
        {'{\n'}
        {entries.map(([key, val], i) => (
          <Fragment key={key}>
            {childPad}
            <span style={{ color: 'var(--text-secondary)' }}>&quot;{key}&quot;</span>
            {': '}
            {colorizeJson(val, indent + 1)}
            {i < entries.length - 1 ? ',' : ''}
            {'\n'}
          </Fragment>
        ))}
        {pad}
        {'}'}
      </>
    )
  }

  return <span>{String(value)}</span>
}

interface JsonViewerProps {
  data: unknown
  collapsible?: boolean
  defaultOpen?: boolean
}

export function JsonViewer({ data, collapsible = true, defaultOpen = true }: JsonViewerProps) {
  const [open, setOpen] = useState(defaultOpen)

  if (data === null || data === undefined) {
    return <div className="font-mono text-xs text-secondary">null</div>
  }

  return (
    <div className="rounded-md border border-border bg-base">
      {collapsible && (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="w-full px-3 py-1.5 text-left text-xs text-secondary transition-colors hover:text-primary"
        >
          {open ? '▾ Collapse' : '▸ Expand'}
        </button>
      )}
      {open && (
        <pre className="overflow-x-auto px-3 pb-3 font-mono text-xs leading-relaxed text-mono">
          {colorizeJson(data, 0)}
        </pre>
      )}
    </div>
  )
}
