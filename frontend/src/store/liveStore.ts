import { create } from 'zustand'
import type { WsEnvelope } from '../types'

export type WsConnectionStatus = 'connecting' | 'connected' | 'disconnected'

interface LiveState {
  status: WsConnectionStatus
  events: WsEnvelope[]
  setStatus: (status: WsConnectionStatus) => void
  pushEvent: (event: WsEnvelope) => void
}

const MAX_EVENTS = 20

export const useLiveStore = create<LiveState>()((set) => ({
  status: 'connecting',
  events: [],
  setStatus: (status) => set({ status }),
  pushEvent: (event) =>
    set((state) => ({ events: [event, ...state.events].slice(0, MAX_EVENTS) })),
}))
