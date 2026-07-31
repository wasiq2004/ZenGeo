import { AlertCircle, CheckCircle2, Info, Loader2, TriangleAlert } from 'lucide-react'
import type { ComponentType, HTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/utils'

const alertStyles = {
  info: { wrapper: 'border-border bg-muted/50 text-foreground', icon: Info, iconClass: 'text-muted-foreground' },
  success: { wrapper: 'border-success/30 bg-success/10 text-foreground', icon: CheckCircle2, iconClass: 'text-success' },
  warning: { wrapper: 'border-warning/35 bg-warning/10 text-foreground', icon: TriangleAlert, iconClass: 'text-warning' },
  error: { wrapper: 'border-destructive/35 bg-destructive/10 text-foreground', icon: AlertCircle, iconClass: 'text-destructive' },
} as const

// `title` is widened from the DOM's string-only attribute to ReactNode, so it
// has to be omitted from the base type rather than merged with it.
export interface AlertProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  variant?: keyof typeof alertStyles
  title?: ReactNode
  icon?: ComponentType<{ className?: string }>
}

export function Alert({
  variant = 'info',
  title,
  icon,
  className,
  children,
  ...props
}: AlertProps) {
  const style = alertStyles[variant]
  const Icon = icon ?? style.icon
  return (
    <div
      // Errors and warnings interrupt; info and success are announced politely.
      role={variant === 'error' || variant === 'warning' ? 'alert' : 'status'}
      className={cn('flex gap-3 rounded-lg border p-3.5 text-sm', style.wrapper, className)}
      {...props}
    >
      <Icon className={cn('mt-0.5 size-4 shrink-0', style.iconClass)} aria-hidden="true" />
      <div className="min-w-0 flex-1 space-y-1">
        {title && <p className="font-medium leading-snug">{title}</p>}
        {children && <div className="text-muted-foreground [&_a]:text-primary [&_a]:underline">{children}</div>}
      </div>
    </div>
  )
}

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('skeleton', className)} aria-hidden="true" {...props} />
}

export function Spinner({ className, label = 'Loading' }: { className?: string; label?: string }) {
  return (
    <span role="status" aria-label={label}>
      <Loader2 className={cn('size-4 animate-spin', className)} aria-hidden="true" />
    </span>
  )
}

export function LoadingScreen({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-3 text-muted-foreground">
      <Loader2 className="size-6 animate-spin" aria-hidden="true" />
      <p className="text-sm" role="status">
        {label}…
      </p>
    </div>
  )
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ComponentType<{ className?: string }>
  title: string
  description?: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border px-6 py-14 text-center',
        className,
      )}
    >
      {Icon && (
        <div className="rounded-full bg-muted p-3">
          <Icon className="size-5 text-muted-foreground" aria-hidden="true" />
        </div>
      )}
      <div className="space-y-1">
        <p className="font-medium">{title}</p>
        {description && (
          <p className="mx-auto max-w-sm text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {action}
    </div>
  )
}
