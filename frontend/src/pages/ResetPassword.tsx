import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { z } from 'zod'
import { AuthLayout } from '@/components/layout/AuthLayout'
import { Button } from '@/components/ui/button'
import { Alert } from '@/components/ui/feedback'
import { Field, Input } from '@/components/ui/input'
import { api, ApiError } from '@/lib/api'

const schema = z
  .object({
    password: z
      .string()
      .min(12, 'Use at least 12 characters')
      .max(128, 'That is longer than 128 characters')
      .refine((v) => new Set(v).size >= 5, 'That password is too repetitive'),
    confirmPassword: z.string(),
  })
  .refine((values) => values.password === values.confirmPassword, {
    message: 'Passwords do not match',
    path: ['confirmPassword'],
  })

type FormValues = z.infer<typeof schema>

export default function ResetPassword() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token') ?? ''
  const [formError, setFormError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null)
    try {
      await api.post('/auth/password-reset/confirm', {
        token,
        new_password: values.password,
      })
      navigate('/login', {
        replace: true,
        state: { notice: 'Password updated. Sign in with your new password.' },
      })
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : 'Something went wrong. Try again.')
    }
  })

  if (!token) {
    return (
      <AuthLayout title="Link not valid">
        <div className="space-y-4">
          <Alert variant="error" title="This reset link is incomplete">
            Open the link directly from your email, or request a new one.
          </Alert>
          <Button asChild variant="outline" className="w-full">
            <Link to="/forgot-password">Request a new link</Link>
          </Button>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title="Choose a new password"
      subtitle="Signing you out of every device."
      footer={
        <Link to="/login" className="font-medium text-primary hover:underline">
          Back to sign in
        </Link>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        {formError && <Alert variant="error">{formError}</Alert>}

        <Field label="New password" error={errors.password?.message} required>
          {(props) => (
            <Input
              {...props}
              {...register('password')}
              type="password"
              autoComplete="new-password"
              autoFocus
              placeholder="••••••••••••"
            />
          )}
        </Field>

        <Field label="Confirm new password" error={errors.confirmPassword?.message} required>
          {(props) => (
            <Input
              {...props}
              {...register('confirmPassword')}
              type="password"
              autoComplete="new-password"
              placeholder="••••••••••••"
            />
          )}
        </Field>

        <Button type="submit" className="w-full" loading={isSubmitting}>
          Update password
        </Button>
      </form>
    </AuthLayout>
  )
}
