import { useEffect, useRef } from 'react'
import { useAuthStore } from '../store/authStore'
import { useLiveStore } from '../store/liveStore'
import type { WsEnvelope } from '../types'

function resolveWsUrl(token: string): string {
  const base: string = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
  const wsBase = base.replace(/^http/, 'ws')
  return `${wsBase}/ws?token=${encodeURIComponent(token)}`
}

const MAX_BACKOFF_MS = 30_000

/**
 * Connects to the live events WebSocket (see CLAUDE.md's event envelope).
 * The server side of this doesn't exist until Phase 7 ships, so today this
 * will retry with backoff and settle into "disconnected" — that's the
 * correct, honest state to show, not a bug.
 */
export function useWebSocket(): void {
  const token = useAuthStore((s) => s.token)
  const setStatus = useLiveStore((s) => s.setStatus)
  const pushEvent = useLiveStore((s) => s.pushEvent)
  const backoffRef = useRef(1000)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const closedByUsRef = useRef(false)

  useEffect(() => {
    if (!token) return undefined

    closedByUsRef.current = false

    const connect = () => {
      setStatus('connecting')
      const socket = new WebSocket(resolveWsUrl(token))
      socketRef.current = socket

      socket.onopen = () => {
        backoffRef.current = 1000
        setStatus('connected')
      }

      socket.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data) as WsEnvelope
          pushEvent(parsed)
        } catch {
          // ignore malformed frames
        }
      }

      socket.onclose = () => {
        setStatus('disconnected')
        if (closedByUsRef.current) return
        timeoutRef.current = setTimeout(connect, backoffRef.current)
        backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS)
      }

      socket.onerror = () => {
        socket.close()
      }
    }

    connect()

    return () => {
      closedByUsRef.current = true
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      socketRef.current?.close()
    }
  }, [token, setStatus, pushEvent])
}
