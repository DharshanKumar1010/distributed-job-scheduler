import { useEffect, useState } from 'react'
import { useToastStore, type ToastItem, type ToastType } from '../store/toastStore'

const TYPE_COLOR: Record<ToastType, string> = {
  info: 'var(--accent)',
  success: 'var(--success)',
  warning: 'var(--warning)',
  error: 'var(--danger)',
}

function ToastCard({ toast, onDismiss }: { toast: ToastItem; onDismiss: (id: string) => void }) {
  const [entered, setEntered] = useState(false)

  useEffect(() => {
    const frame = requestAnimationFrame(() => setEntered(true))
    return () => cancelAnimationFrame(frame)
  }, [])

  return (
    <div
      role="status"
      onClick={() => onDismiss(toast.id)}
      className="w-80 max-w-[calc(100vw-2rem)] cursor-pointer rounded-md border border-border bg-elevated px-4 py-3 text-sm text-primary shadow-lg"
      style={{
        borderLeft: `3px solid ${TYPE_COLOR[toast.type]}`,
        transform: entered ? 'translateX(0)' : 'translateX(120%)',
        opacity: entered ? 1 : 0,
        transition: 'transform 200ms ease-out, opacity 200ms ease-out',
      }}
    >
      {toast.message}
    </div>
  )
}

export function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts)
  const dismissToast = useToastStore((s) => s.dismissToast)

  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col-reverse gap-2">
      {toasts.map((toast) => (
        <ToastCard key={toast.id} toast={toast} onDismiss={dismissToast} />
      ))}
    </div>
  )
}
