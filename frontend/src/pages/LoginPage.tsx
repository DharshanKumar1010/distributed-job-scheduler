import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getPermissions, login as loginRequest } from '../api/auth'
import { getErrorMessage } from '../api/client'
import { Logo } from '../components/Logo'
import { useAuthStore } from '../store/authStore'

const inputClass =
  'w-full rounded-md border border-border bg-elevated px-3 py-2 text-sm text-primary outline-none transition-shadow focus:shadow-[0_0_0_2px_var(--accent-glow)]'

export function LoginPage() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.login)
  const setPermissions = useAuthStore((s) => s.setPermissions)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: loginRequest,
    onSuccess: async (result) => {
      setAuth(result.access_token, result.user)
      try {
        const perms = await getPermissions()
        setPermissions(perms.permissions, perms.role, perms.cannot_do)
      } catch {
        // non-fatal - UI just won't have granular gating until next fetch
      }
      navigate('/dashboard')
    },
    onError: (error) => setFormError(getErrorMessage(error)),
  })

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    setFormError(null)
    if (!email || !password) {
      setFormError('Email and password are required')
      return
    }
    mutation.mutate({ email, password })
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-base">
      <div className="w-[400px] rounded-lg border border-border bg-card p-8">
        <div className="mb-6 flex justify-center">
          <Logo />
        </div>
        <h1 className="mb-6 text-center font-display text-lg text-primary">Sign in</h1>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div>
            <label className="mb-1.5 block text-xs uppercase tracking-wide text-secondary" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={inputClass}
            />
          </div>
          <div>
            <label
              className="mb-1.5 block text-xs uppercase tracking-wide text-secondary"
              htmlFor="password"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={inputClass}
            />
          </div>

          {formError && <p className="text-sm text-danger">{formError}</p>}

          <button
            type="submit"
            disabled={mutation.isPending}
            className="w-full rounded-md bg-accent py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {mutation.isPending ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-secondary">
          Don&apos;t have an account?{' '}
          <Link to="/register" className="text-accent hover:underline">
            Register
          </Link>
        </p>
      </div>
    </div>
  )
}
