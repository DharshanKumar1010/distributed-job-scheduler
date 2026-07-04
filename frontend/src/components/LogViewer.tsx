import { formatTimestamp } from '../lib/format'
import type { JobLog, LogLevel } from '../types'

const LEVEL_COLORS: Record<LogLevel, string> = {
  debug: 'var(--text-secondary)',
  info: 'var(--text-primary)',
  warning: 'var(--warning)',
  error: 'var(--danger)',
}

interface LogViewerProps {
  logs: JobLog[]
  maxHeight?: string
}

// Logs are capped server-side (100 most recent), so a plain scroll container
// is enough here — no need for a windowing library on top of that.
export function LogViewer({ logs, maxHeight = '360px' }: LogViewerProps) {
  if (logs.length === 0) {
    return (
      <div className="rounded-md border border-border bg-base py-6 text-center text-sm text-secondary">
        No logs yet
      </div>
    )
  }

  return (
    <div
      className="overflow-y-auto rounded-md border border-border bg-base font-mono text-xs"
      style={{ maxHeight }}
    >
      {logs.map((log) => (
        <div key={log.id} className="flex gap-3 border-b border-border px-3 py-1.5 last:border-b-0">
          <span className="shrink-0 text-secondary">{formatTimestamp(log.timestamp)}</span>
          <span className="w-14 shrink-0 uppercase" style={{ color: LEVEL_COLORS[log.level] }}>
            {log.level}
          </span>
          <span className="whitespace-pre-wrap break-all" style={{ color: LEVEL_COLORS[log.level] }}>
            {log.message}
          </span>
        </div>
      ))}
    </div>
  )
}
