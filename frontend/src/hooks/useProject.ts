import { useQuery } from '@tanstack/react-query'
import { createProject, listProjects } from '../api/projects'
import { useAuthStore } from '../store/authStore'

/** This app doesn't expose project management UI (out of Phase 6 scope), so
 * it transparently uses the org's first project, creating one if needed. */
export function useDefaultProject() {
  const orgId = useAuthStore((s) => s.user?.org_id)

  return useQuery({
    queryKey: ['default-project', orgId],
    queryFn: async () => {
      const projects = await listProjects(orgId as string)
      if (projects.length > 0) return projects[0]
      return createProject(orgId as string, { name: 'Default', slug: 'default' })
    },
    enabled: !!orgId,
    staleTime: Infinity,
  })
}
