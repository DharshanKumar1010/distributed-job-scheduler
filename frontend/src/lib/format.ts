export function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour12: false })
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString()
}

export function formatRelativeAge(iso: string): string {
  const then = new Date(iso).getTime()
  const diffSeconds = Math.max(0, Math.floor((Date.now() - then) / 1000))

  if (diffSeconds < 60) return `${diffSeconds}s ago`
  const diffMinutes = Math.floor(diffSeconds / 60)
  if (diffMinutes < 60) return `${diffMinutes}m ago`
  const diffHours = Math.floor(diffMinutes / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.floor(diffHours / 24)
  return `${diffDays}d ago`
}

export function truncateId(id: string, length = 8): string {
  return `${id.slice(0, length)}…`
}
