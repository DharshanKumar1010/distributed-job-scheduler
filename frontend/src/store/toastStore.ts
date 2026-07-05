import { create } from 'zustand'

export type ToastType = 'info' | 'success' | 'warning' | 'error'

export interface ToastItem {
  id: string
  type: ToastType
  message: string
  actionHref?: string
}

interface ToastState {
  toasts: ToastItem[]
  addToast: (type: ToastType, message: string, actionHref?: string) => void
  dismissToast: (id: string) => void
}

const MAX_TOASTS = 5
const AUTO_DISMISS_MS = 3000

export const useToastStore = create<ToastState>()((set, get) => ({
  toasts: [],
  addToast: (type, message, actionHref) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`
    set((state) => {
      const next = [...state.toasts, { id, type, message, actionHref }]
      return { toasts: next.length > MAX_TOASTS ? next.slice(next.length - MAX_TOASTS) : next }
    })
    setTimeout(() => get().dismissToast(id), AUTO_DISMISS_MS)
  },
  dismissToast: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}))
