import { useAuthStore } from '../store/authStore'

export function usePermissions() {
  const permissions = useAuthStore((s) => s.permissions)
  const cannotDo = useAuthStore((s) => s.cannotDo)
  const role = useAuthStore((s) => s.role)

  const can = (permission: string): boolean => permissions.includes(permission)
  const cannot = (permission: string): boolean => !permissions.includes(permission)

  return { can, cannot, role, permissions, cannotDo }
}
