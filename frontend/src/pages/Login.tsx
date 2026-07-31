import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { AuthLayout } from '@/components/layout/AuthLayout'
import { Button } from '@/components/ui/button'
import { Alert } from '@/components/ui/feedback'
import { Field, Input } from '@/components/ui/input'
import { ApiError } from '@/lib/api'
import { useAuth } from '@/lib/auth'

const schema = z.object({
  email: z.string().min(1, 'Enter your email address').email('That does not look like an email'),
  password: z.string().min(1, 'Enter your password'),
  totpCode: z.string().optional(),
})

type FormValues = z.infer<typeof schema>

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [formError, setFormError] = useState<string | null>(null)
  const [needsMfa, setNeedsMfa] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  // Where the user was headed before being bounced to /login.
  const from = (location.state as { from?: string } | null)?.from

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null)
    try {
      const user = await login(values.email, values.password, values.totpCode || undefined)
      // One login page for everyone: the role decides the destination. The
      // server enforces the same boundary on every request.
      const home = user.role === 'admin' ? '/admin' : '/app'
      navigate(from && from.startsWith(home) ? from : home, { replace: true })
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.detail === 'A two-factor authentication code is required') {
          setNeedsMfa(true)
          setFormError('Enter the 6-digit code from your authenticator app.')
          return
        }
        setFormError(error.message)
      } else {
        setFormError('Could not reach the server. Check your connection and try again.')
      }
    }
  })

  return (
    <AuthLayout
      title="Sign in"
      subtitle="One account for the whole platform."
      footer={
        <>
          New here?{' '}
          <Link to="/signup" className="font-medium text-primary hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        {formError && <Alert variant="error">{formError}</Alert>}

        <Field label="Email" error={errors.email?.message} required>
          {(props) => (
            <Input
              {...props}
              {...register('email')}
              type="email"
              autoComplete="email"
              autoFocus
              placeholder="you@company.com"
            />
          )}
        </Field>

        <Field label="Password" error={errors.password?.message} required>
          {(props) => (
            <Input
              {...props}
              {...register('password')}
              type="password"
              autoComplete="current-password"
              placeholder="••••••••••••"
            />
          )}
        </Field>

        {needsMfa && (
          <Field
            label="Authentication code"
            hint="6-digit code from your authenticator app"
            error={errors.totpCode?.message}
            required
          >
            {(props) => (
              <Input
                {...props}
                {...register('totpCode')}
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="123456"
                maxLength={8}
                autoFocus
              />
            )}
          </Field>
        )}

        {/* No "forgot password" link: this deployment sends no email, so there
            is no self-service reset. An administrator sets a new password and
            hands it over directly. */}

        <Button type="submit" className="w-full" loading={isSubmitting}>
          Sign in
        </Button>
      </form>
    </AuthLayout>
  )
}
