import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User } from '../types'

interface AuthState {
  token: string | null
  user: User | null
  isAuthenticated: boolean
  permissions: string[]
  cannotDo: string[]
  role: string | null
  login: (token: string, user: User) => void
  logout: () => void
  setPermissions: (permissions: string[], role: string, cannotDo: string[]) => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isAuthenticated: false,
      permissions: [],
      cannotDo: [],
      role: null,
      login: (token, user) => set({ token, user, isAuthenticated: true }),
      logout: () =>
        set({ token: null, user: null, isAuthenticated: false, permissions: [], cannotDo: [], role: null }),
      setPermissions: (permissions, role, cannotDo) => set({ permissions, role, cannotDo }),
    }),
    {
      name: 'scheduler-auth',
    },
  ),
)
