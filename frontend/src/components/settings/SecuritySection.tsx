import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { LogOut, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert } from '@/components/ui/feedback'
import { Field, Input } from '@/components/ui/input'
import { useToast } from '@/components/ui/toast'
import { api, ApiError } from '@/lib/api'
import { useAuth } from '@/lib/auth'

const passwordSchema = z
  .object({
    currentPassword: z.string().min(1, 'Enter your current password'),
    newPassword: z
      .string()
      .min(12, 'Use at least 12 characters')
      .max(128)
      .refine((v) => new Set(v).size >= 5, 'That password is too repetitive'),
    confirmPassword: z.string(),
  })
  .refine((v) => v.newPassword === v.confirmPassword, {
    message: 'Passwords do not match',
    path: ['confirmPassword'],
  })

export function SecuritySection() {
  const { user, logout } = useAuth()
  const { toast } = useToast()
  const navigate = useNavigate()
  const [formError, setFormError] = useState<string | null>(null)

  const form = useForm<z.infer<typeof passwordSchema>>({ resolver: zodResolver(passwordSchema) })

  const changePassword = useMutation({
    mutationFn: (values: z.infer<typeof passwordSchema>) =>
      api.post('/auth/change-password', {
        current_password: values.currentPassword,
        new_password: values.newPassword,
      }),
    onSuccess: async () => {
      setFormError(null)
      form.reset()
      toast({
        title: 'Password changed',
        description: 'Signing you out — sign in again with your new password.',
        variant: 'success',
      })
      // The server revoked every session, including this one.
      setTimeout(() => void logout().then(() => navigate('/login', { replace: true })), 1200)
    },
    onError: (error) =>
      setFormError(error instanceof ApiError ? error.message : 'Something went wrong.'),
  })

  const signOutEverywhere = useMutation({
    mutationFn: () => api.post<{ detail: string }>('/auth/logout-all'),
    onSuccess: (result) => {
      toast({ title: result.detail, variant: 'success' })
      setTimeout(() => navigate('/login', { replace: true }), 1000)
    },
    onError: () => toast({ title: 'Could not sign out everywhere', variant: 'error' }),
  })

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Password</CardTitle>
          <CardDescription>
            Changing your password signs you out of every device, including this one.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={form.handleSubmit((v) => changePassword.mutate(v))}
            className="max-w-sm space-y-4"
            noValidate
          >
            {formError && <Alert variant="error">{formError}</Alert>}

            <Field
              label="Current password"
              error={form.formState.errors.currentPassword?.message}
              required
            >
              {(props) => (
                <Input
                  {...props}
                  {...form.register('currentPassword')}
                  type="password"
                  autoComplete="current-password"
                />
              )}
            </Field>
            <Field
              label="New password"
              hint="At least 12 characters"
              error={form.formState.errors.newPassword?.message}
              required
            >
              {(props) => (
                <Input
                  {...props}
                  {...form.register('newPassword')}
                  type="password"
                  autoComplete="new-password"
                />
              )}
            </Field>
            <Field
              label="Confirm new password"
              error={form.formState.errors.confirmPassword?.message}
              required
            >
              {(props) => (
                <Input
                  {...props}
                  {...form.register('confirmPassword')}
                  type="password"
                  autoComplete="new-password"
                />
              )}
            </Field>
            <Button type="submit" loading={changePassword.isPending}>
              Change password
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Two-factor authentication
            {user?.mfa_enabled ? (
              <Badge variant="success" className="gap-1">
                <ShieldCheck aria-hidden="true" /> On
              </Badge>
            ) : (
              <Badge variant="muted">Off</Badge>
            )}
          </CardTitle>
          <CardDescription>
            {user?.role === 'admin'
              ? 'Strongly recommended for administrator accounts.'
              : 'Adds a one-time code from your authenticator app at sign-in.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <MfaControls />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Active sessions</CardTitle>
          <CardDescription>
            If you signed in on a shared or lost device, revoke every session at once.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            variant="outline"
            loading={signOutEverywhere.isPending}
            onClick={() => signOutEverywhere.mutate()}
          >
            <LogOut aria-hidden="true" /> Sign out everywhere
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

function MfaControls() {
  const { user, refreshUser } = useAuth()
  const { toast } = useToast()
  const [secret, setSecret] = useState<string | null>(null)
  const [uri, setUri] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  const startSetup = useMutation({
    mutationFn: () => api.post<{ secret: string; otpauth_uri: string }>('/auth/mfa/setup'),
    onSuccess: (data) => {
      setSecret(data.secret)
      setUri(data.otpauth_uri)
      setError(null)
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : 'Could not start setup.'),
  })

  const activate = useMutation({
    mutationFn: () => api.post('/auth/mfa/activate', { code }),
    onSuccess: async () => {
      setSecret(null)
      setUri(null)
      setCode('')
      await refreshUser()
      toast({ title: 'Two-factor authentication is on', variant: 'success' })
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : 'That code was not accepted.'),
  })

  const disable = useMutation({
    mutationFn: () => api.post('/auth/mfa/disable', { password }),
    onSuccess: async () => {
      setPassword('')
      await refreshUser()
      toast({ title: 'Two-factor authentication is off' })
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : 'Could not turn it off.'),
  })

  if (user?.mfa_enabled) {
    return (
      <div className="max-w-sm space-y-3">
        {error && <Alert variant="error">{error}</Alert>}
        <Field label="Password" hint="Confirms it is really you" required>
          {(props) => (
            <Input
              {...props}
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
        </Field>
        <Button
          variant="outline"
          loading={disable.isPending}
          disabled={!password}
          onClick={() => disable.mutate()}
        >
          Turn off two-factor
        </Button>
      </div>
    )
  }

  if (secret) {
    return (
      <div className="max-w-md space-y-4">
        {error && <Alert variant="error">{error}</Alert>}
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">
            Add this secret to your authenticator app, then enter the 6-digit code it shows.
          </p>
          <code className="block break-all rounded-md bg-muted p-3 font-mono text-sm">
            {secret}
          </code>
          {uri && (
            <p className="break-all text-xs text-muted-foreground">
              Or use this setup URI: <span className="font-mono">{uri}</span>
            </p>
          )}
        </div>
        <Field label="Authentication code" required>
          {(props) => (
            <Input
              {...props}
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={8}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="123456"
            />
          )}
        </Field>
        <div className="flex gap-2">
          <Button loading={activate.isPending} disabled={code.length < 6} onClick={() => activate.mutate()}>
            Confirm and enable
          </Button>
          <Button variant="ghost" onClick={() => setSecret(null)}>
            Cancel
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {error && <Alert variant="error">{error}</Alert>}
      <Button variant="outline" loading={startSetup.isPending} onClick={() => startSetup.mutate()}>
        <ShieldCheck aria-hidden="true" /> Set up two-factor
      </Button>
    </div>
  )
}
