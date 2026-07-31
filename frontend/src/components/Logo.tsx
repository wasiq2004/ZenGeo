import { cn } from '@/lib/utils'

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn('size-8', className)} aria-hidden="true">
      <defs>
        <linearGradient id="geo-logo-gradient" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="hsl(246 84% 66%)" />
          <stop offset="1" stopColor="hsl(276 76% 62%)" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="url(#geo-logo-gradient)" />
      <path
        d="M22 12.2A6.6 6.6 0 0 0 10.2 15a6.6 6.6 0 0 0 10.6 5.3l3.4 3.4"
        fill="none"
        stroke="white"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <circle cx="16" cy="15" r="2.6" fill="white" />
    </svg>
  )
}

export function Logo({ className, showText = true }: { className?: string; showText?: boolean }) {
  return (
    <span className={cn('inline-flex items-center gap-2.5', className)}>
      <LogoMark />
      {showText && (
        <span className="text-[15px] font-semibold tracking-tight">
          CheckGEO<span className="text-muted-foreground">.ai</span>
        </span>
      )}
    </span>
  )
}
