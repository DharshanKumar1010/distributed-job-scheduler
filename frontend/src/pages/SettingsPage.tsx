import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { inviteUser, listOrgUsers, removeUser, updateUserRole } from '../api/organizations'
import { getErrorMessage } from '../api/client'
import { ErrorState } from '../components/ErrorState'
import { PageHeader } from '../components/PageHeader'
import { Skeleton } from '../components/Skeleton'
import { StatusBadge } from '../components/StatusBadge'
import { usePermissions } from '../hooks/usePermissions'
import { useAuthStore } from '../store/authStore'
import { useToastStore } from '../store/toastStore'
import type { User, UserRole } from '../types'

const ROLE_OPTIONS: UserRole[] = ['owner', 'admin', 'member', 'viewer']
const AVATAR_COLORS = ['#6366F1', '#10B981', '#F59E0B', '#EF4444', '#3B82F6', '#EC4899']

function avatarColor(seed: string): string {
  let hash = 0
  for (let i = 0; i < seed.length; i++) hash = (hash * 31 + seed.charCodeAt(i)) >>> 0
  return AVATAR_COLORS[hash % AVATAR_COLORS.length]
}

function initials(user: User): string {
  const source = user.full_name?.trim() || user.email
  const parts = source.split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return source.slice(0, 2).toUpperCase()
}

function RoleCell({ member, orgId, isSelf }: { member: User; orgId: string; isSelf: boolean }) {
  const { can, role: myRole } = usePermissions()
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: (role: string) => updateUserRole(orgId, member.id, role),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['org-users', orgId] }),
  })

  if (isSelf || !can('user:update_role')) {
    return <StatusBadge status={member.role} label={member.role} />
  }

  return (
    <select
      value={member.role}
      disabled={mutation.isPending}
      onChange={(e) => mutation.mutate(e.target.value)}
      className="rounded-md border border-border bg-elevated px-2 py-1 text-xs text-primary outline-none disabled:opacity-50"
    >
      {ROLE_OPTIONS.map((r) => (
        <option key={r} value={r} disabled={r === 'owner' && myRole !== 'owner'}>
          {r}
        </option>
      ))}
    </select>
  )
}

function TeamMembersSection() {
  const orgId = useAuthStore((s) => s.user?.org_id)
  const currentUserId = useAuthStore((s) => s.user?.id)
  const { can } = usePermissions()
  const queryClient = useQueryClient()

  const { data: users, isLoading, isError, refetch } = useQuery({
    queryKey: ['org-users', orgId],
    queryFn: () => listOrgUsers(orgId as string),
    enabled: !!orgId,
  })

  const removeMutation = useMutation({
    mutationFn: (userId: string) => removeUser(orgId as string, userId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['org-users', orgId] }),
  })

  if (isLoading) {
    return (
      <div className="rounded-lg border border-border bg-card p-5">
        <Skeleton rows={4} />
      </div>
    )
  }

  if (isError) {
    return <ErrorState message="Couldn't load team members" onRetry={() => refetch()} />
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wider text-secondary">
            <th className="px-4 py-3 font-medium">Member</th>
            <th className="px-4 py-3 font-medium">Role</th>
            <th className="px-4 py-3 font-medium">Joined</th>
            <th className="px-4 py-3 font-medium">Actions</th>
          </tr>
        </thead>
        <tbody>
          {(users ?? []).map((member) => {
            const isSelf = member.id === currentUserId
            return (
              <tr key={member.id} className="border-t border-border">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-medium text-white"
                      style={{ backgroundColor: avatarColor(member.id) }}
                    >
                      {initials(member)}
                    </div>
                    <div className="min-w-0">
                      <div className="truncate text-primary">{member.full_name || member.email}</div>
                      <div className="truncate font-mono text-xs text-mono">{member.email}</div>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <RoleCell member={member} orgId={orgId as string} isSelf={isSelf} />
                </td>
                <td className="px-4 py-3 font-mono text-xs text-mono">—</td>
                <td className="px-4 py-3">
                  {can('user:remove') && !isSelf && (
                    <button
                      type="button"
                      onClick={() => {
                        if (window.confirm(`Remove ${member.email} from this organization?`)) {
                          removeMutation.mutate(member.id)
                        }
                      }}
                      disabled={removeMutation.isPending}
                      className="text-xs text-danger hover:underline disabled:opacity-50"
                    >
                      Remove
                    </button>
                  )}
                  {isSelf && <span className="text-xs text-secondary">—</span>}
                </td>
              </tr>
            )
          })}
          {(users ?? []).length === 0 && (
            <tr>
              <td colSpan={4} className="px-4 py-8 text-center text-secondary">
                No team members yet
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

function InviteMemberForm() {
  const orgId = useAuthStore((s) => s.user?.org_id)
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<UserRole>('member')
  const [formError, setFormError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () => inviteUser(orgId as string, { email, role }),
    onSuccess: (result) => {
      queryClient.setQueryData<User[]>(['org-users', orgId], (old) =>
        old ? [...old, result.user] : old,
      )
      addToast('success', `Invited ${result.user.email} as ${result.user.role}`)
      // There's no outbound email system in this app - the temporary
      // password has to be handed to the admin directly, right now, or it's
      // lost and the invited user can never log in.
      window.alert(
        `${result.user.email} was invited.\n\nTemporary password: ${result.temporary_password}\n\nShare this with them securely - it won't be shown again.`,
      )
      setEmail('')
      setRole('member')
      setFormError(null)
    },
    onError: (error) => setFormError(getErrorMessage(error)),
  })

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!email.trim()) return
    mutation.mutate()
  }

  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <div className="mb-3 text-xs uppercase tracking-widest text-secondary">Invite Member</div>
      <form onSubmit={handleSubmit} className="flex items-end gap-3">
        <div className="flex-1">
          <label className="mb-1.5 block text-xs text-secondary">Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="name@company.com"
            className="w-full rounded-md border border-border bg-elevated px-3 py-2 text-sm text-primary outline-none focus:shadow-[0_0_0_2px_var(--accent-glow)]"
          />
        </div>
        <div>
          <label className="mb-1.5 block text-xs text-secondary">Role</label>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as UserRole)}
            className="rounded-md border border-border bg-elevated px-3 py-2 text-sm text-primary outline-none"
          >
            <option value="admin">admin</option>
            <option value="member">member</option>
            <option value="viewer">viewer</option>
          </select>
        </div>
        <button
          type="submit"
          disabled={mutation.isPending || !email.trim()}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {mutation.isPending ? 'Inviting…' : 'Invite'}
        </button>
      </form>
      {formError && <div className="mt-2 text-xs text-danger">{formError}</div>}
    </div>
  )
}

function PermissionsPanel() {
  const { role, permissions, cannotDo } = usePermissions()
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-xs uppercase tracking-widest text-secondary">Your Permissions</div>
        {role && <StatusBadge status={role} label={role} />}
      </div>

      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="text-sm text-accent hover:underline"
      >
        {expanded ? 'Hide' : 'Show'} {permissions.length} permission{permissions.length === 1 ? '' : 's'}
      </button>

      {expanded && (
        <div className="mt-3 space-y-4">
          <div>
            <div className="mb-1.5 text-xs text-secondary">Granted</div>
            <div className="flex flex-wrap gap-1.5">
              {permissions.map((p) => (
                <span
                  key={p}
                  className="rounded-full border border-border bg-elevated px-2 py-0.5 font-mono text-xs text-success"
                >
                  {p}
                </span>
              ))}
            </div>
          </div>
          {cannotDo.length > 0 && (
            <div>
              <div className="mb-1.5 text-xs text-secondary">Not available on your role</div>
              <div className="flex flex-wrap gap-1.5">
                {cannotDo.map((p) => (
                  <span
                    key={p}
                    title="Upgrade to admin to unlock these"
                    className="rounded-full border border-border bg-elevated px-2 py-0.5 font-mono text-xs text-secondary opacity-50"
                  >
                    {p}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function SettingsPage() {
  const { can } = usePermissions()

  return (
    <div>
      <PageHeader title="Settings" description="Manage your team and review your permissions" />

      <div className="space-y-6">
        <TeamMembersSection />
        {can('user:invite') && <InviteMemberForm />}
        <PermissionsPanel />
      </div>
    </div>
  )
}
