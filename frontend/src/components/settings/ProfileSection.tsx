import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { MailCheck, MailWarning } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert } from '@/components/ui/feedback'
import { Field, Input, Label } from '@/components/ui/input'
import { Switch } from '@/components/ui/misc'
import { useToast } from '@/components/ui/toast'
import { api, ApiError } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import type { User } from '@/lib/types'

const profileSchema = z.object({
  fullName: z.string().max(200).optional(),
})

const emailSchema = z.object({
  newEmail: z.string().min(1, 'Enter an email address').email('That does not look like an email'),
  password: z.string().min(1, 'Enter your current password'),
})

export function ProfileSection() {
  const { user, setUser, refreshUser } = useAuth()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [emailError, setEmailError] = useState<string | null>(null)
  const [emailSent, setEmailSent] = useState(false)

  const profileForm = useForm<z.infer<typeof profileSchema>>({
    resolver: zodResolver(profileSchema),
    defaultValues: { fullName: user?.full_name ?? '' },
  })

  const emailForm = useForm<z.infer<typeof emailSchema>>({ resolver: zodResolver(emailSchema) })

  const saveProfile = useMutation({
    mutationFn: (values: z.infer<typeof profileSchema>) =>
      api.patch<User>('/users/me', { full_name: values.fullName || null }),
    onSuccess: (updated) => {
      setUser(updated)
      toast({ title: 'Profile saved', variant: 'success' })
    },
    onError: (error) =>
      toast({
        title: 'Could not save profile',
        description: error instanceof ApiError ? error.message : undefined,
        variant: 'error',
      }),
  })

  const toggleNotifications = useMutation({
    mutationFn: (enabled: boolean) =>
      api.patch<User>('/users/me', { notify_audit_complete: enabled }),
    onSuccess: (updated) => {
      setUser(updated)
      queryClient.invalidateQueries({ queryKey: ['me'] })
    },
    onError: () => toast({ title: 'Could not update notifications', variant: 'error' }),
  })

  const changeEmail = useMutation({
    mutationFn: (values: z.infer<typeof emailSchema>) =>
      api.post('/users/me/email', { new_email: values.newEmail, password: values.password }),
    onSuccess: async () => {
      setEmailError(null)
      emailForm.reset()
      await refreshUser()
      toast({
        title: 'Email updated',
        description: 'Check the new address for a confirmation link.',
        variant: 'success',
      })
    },
    onError: (error) =>
      setEmailError(error instanceof ApiError ? error.message : 'Something went wrong.'),
  })

  const resendVerification = useMutation({
    mutationFn: () => api.post('/users/me/resend-verification'),
    onSuccess: () => setEmailSent(true),
  })

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Profile</CardTitle>
          <CardDescription>How you appear inside the app.</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={profileForm.handleSubmit((v) => saveProfile.mutate(v))}
            className="max-w-sm space-y-4"
          >
            <Field label="Name" error={profileForm.formState.errors.fullName?.message}>
              {(props) => (
                <Input {...props} {...profileForm.register('fullName')} placeholder="Alex Kim" />
              )}
            </Field>
            <Button type="submit" loading={saveProfile.isPending}>
              Save
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Email address
            {user?.is_email_verified ? (
              <Badge variant="success" className="gap-1">
                <MailCheck aria-hidden="true" /> Confirmed
              </Badge>
            ) : (
              <Badge variant="warning" className="gap-1">
                <MailWarning aria-hidden="true" /> Unconfirmed
              </Badge>
            )}
          </CardTitle>
          <CardDescription>
            Currently <span className="font-medium text-foreground">{user?.email}</span>. Changing
            it requires confirming the new address before you can run audits again.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!user?.is_email_verified && (
            <Alert variant="warning" title="Confirm your email to run audits">
              {emailSent ? (
                'A new confirmation link is on its way.'
              ) : (
                <Button
                  variant="link"
                  size="sm"
                  className="h-auto p-0"
                  loading={resendVerification.isPending}
                  onClick={() => resendVerification.mutate()}
                >
                  Send a new confirmation link
                </Button>
              )}
            </Alert>
          )}

          <form
            onSubmit={emailForm.handleSubmit((v) => changeEmail.mutate(v))}
            className="max-w-sm space-y-4"
          >
            {emailError && <Alert variant="error">{emailError}</Alert>}
            <Field label="New email" error={emailForm.formState.errors.newEmail?.message} required>
              {(props) => (
                <Input
                  {...props}
                  {...emailForm.register('newEmail')}
                  type="email"
                  autoComplete="email"
                  placeholder="new@company.com"
                />
              )}
            </Field>
            <Field
              label="Current password"
              hint="Confirms it is really you making this change"
              error={emailForm.formState.errors.password?.message}
              required
            >
              {(props) => (
                <Input
                  {...props}
                  {...emailForm.register('password')}
                  type="password"
                  autoComplete="current-password"
                />
              )}
            </Field>
            <Button type="submit" variant="outline" loading={changeEmail.isPending}>
              Change email
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Notifications</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between gap-6 rounded-lg border border-border p-4">
            <div className="space-y-0.5">
              <Label htmlFor="notify-complete">Email me when an audit finishes</Label>
              <p className="text-sm text-muted-foreground">
                Audits with many Share of Voice prompts can take a while — we will tell you when
                the report is ready.
              </p>
            </div>
            <Switch
              id="notify-complete"
              checked={user?.notify_audit_complete ?? true}
              onCheckedChange={(checked) => toggleNotifications.mutate(checked)}
              disabled={toggleNotifications.isPending}
            />
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
