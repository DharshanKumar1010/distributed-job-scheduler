import { create } from 'zustand'
import type { WsEnvelope } from '../types'

export type WsConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'reconnecting'

interface LiveState {
  status: WsConnectionStatus
  events: WsEnvelope[]
  reconnectAttempt: number
  setStatus: (status: WsConnectionStatus) => void
  setReconnectAttempt: (attempt: number) => void
  pushEvent: (event: WsEnvelope) => void
}

const MAX_EVENTS = 50

export const useLiveStore = create<LiveState>()((set) => ({
  status: 'connecting',
  events: [],
  reconnectAttempt: 0,
  setStatus: (status) => set({ status }),
  setReconnectAttempt: (reconnectAttempt) => set({ reconnectAttempt }),
  pushEvent: (event) =>
    set((state) => ({ events: [event, ...state.events].slice(0, MAX_EVENTS) })),
}))
