import { zodResolver } from '@hookform/resolvers/zod'
import { Check } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { AuthLayout } from '@/components/layout/AuthLayout'
import { Button } from '@/components/ui/button'
import { Alert } from '@/components/ui/feedback'
import { Field, Input } from '@/components/ui/input'
import { ApiError } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/utils'

// Mirrors the server-side policy in backend/app/schemas/auth.py. The server is
// authoritative; this only gives faster feedback.
const MIN_PASSWORD_LENGTH = 12

const schema = z
  .object({
    fullName: z.string().max(200).optional(),
    email: z.string().min(1, 'Enter your email address').email('That does not look like an email'),
    password: z
      .string()
      .min(MIN_PASSWORD_LENGTH, `Use at least ${MIN_PASSWORD_LENGTH} characters`)
      .max(128, 'That is longer than 128 characters')
      .refine((v) => new Set(v).size >= 5, 'That password is too repetitive'),
    confirmPassword: z.string(),
  })
  .refine((values) => values.password === values.confirmPassword, {
    message: 'Passwords do not match',
    path: ['confirmPassword'],
  })

type FormValues = z.infer<typeof schema>

function PasswordChecklist({ value }: { value: string }) {
  const rules = [
    { label: `At least ${MIN_PASSWORD_LENGTH} characters`, ok: value.length >= MIN_PASSWORD_LENGTH },
    { label: 'At least 5 different characters', ok: new Set(value).size >= 5 },
  ]
  return (
    <ul className="space-y-1" aria-live="polite">
      {rules.map((rule) => (
        <li
          key={rule.label}
          className={cn(
            'flex items-center gap-1.5 text-xs',
            rule.ok ? 'text-success' : 'text-muted-foreground',
          )}
        >
          <Check className={cn('size-3', !rule.ok && 'opacity-30')} aria-hidden="true" />
          {rule.label}
        </li>
      ))}
    </ul>
  )
}

export default function Signup() {
  const { signup } = useAuth()
  const navigate = useNavigate()
  const [formError, setFormError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema), mode: 'onBlur' })

  const password = watch('password') ?? ''

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null)
    try {
      await signup(values.email, values.password, values.fullName || undefined)
      // New accounts are always role "user" - promotion is admin-only.
      navigate('/app', { replace: true })
    } catch (error) {
      setFormError(
        error instanceof ApiError
          ? error.message
          : 'Could not reach the server. Check your connection and try again.',
      )
    }
  })

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Free, and your API keys stay yours."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-primary hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        {formError && <Alert variant="error">{formError}</Alert>}

        <Field label="Name" hint="Optional" error={errors.fullName?.message}>
          {(props) => (
            <Input {...props} {...register('fullName')} autoComplete="name" placeholder="Alex Kim" />
          )}
        </Field>

        <Field label="Email" error={errors.email?.message} required>
          {(props) => (
            <Input
              {...props}
              {...register('email')}
              type="email"
              autoComplete="email"
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
              autoComplete="new-password"
              placeholder="••••••••••••"
            />
          )}
        </Field>

        <PasswordChecklist value={password} />

        <Field label="Confirm password" error={errors.confirmPassword?.message} required>
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
          Create account
        </Button>

        <p className="text-center text-xs leading-relaxed text-muted-foreground">
          We send one confirmation email. Confirming it unlocks running audits.
        </p>
      </form>
    </AuthLayout>
  )
}
