import {
  ChevronDown,
  LayoutDashboard,
  LogOut,
  Menu,
  Settings,
  Shield,
  User as UserIcon,
  X,
} from 'lucide-react'
import { useEffect, useState, type ComponentType } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { Logo, LogoMark } from '@/components/Logo'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ImpersonationBanner } from '@/components/ImpersonationBanner'
import { useAuth } from '@/lib/auth'
import { initials } from '@/lib/format'
import { cn } from '@/lib/utils'

export interface NavItem {
  to: string
  label: string
  icon: ComponentType<{ className?: string }>
  end?: boolean
}

export function AppShell({
  items,
  variant = 'user',
  children,
}: {
  items: NavItem[]
  variant?: 'user' | 'admin'
  children: React.ReactNode
}) {
  const { user, isAdmin, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)

  // Close the mobile drawer whenever the route changes.
  useEffect(() => setMobileOpen(false), [location.pathname])

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  const nav = (
    <nav className="flex flex-1 flex-col gap-1 p-3" aria-label="Sections">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
              isActive
                ? 'bg-primary/12 text-primary'
                : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
            )
          }
        >
          <item.icon className="size-4 shrink-0" aria-hidden="true" />
          {item.label}
        </NavLink>
      ))}
    </nav>
  )

  return (
    // Explicit `font-app` even though it is the inherited default - the shell is
    // the boundary of the authenticated product, and stating it here keeps the
    // landing font from ever leaking in through a shared ancestor.
    //
    // The impersonation banner wraps the whole shell rather than sitting inside
    // the content column, so it is present on every authenticated screen -
    // user side and admin side alike - and cannot be scrolled away from.
    <div className="min-h-screen bg-background font-app">
      <ImpersonationBanner />
      <div className="flex min-h-screen">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
      >
        Skip to content
      </a>

      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-border bg-card lg:flex">
        <div className="flex h-16 items-center gap-2 border-b border-border px-5">
          <Link to={isAdmin ? '/admin' : '/app'} className="rounded-md focus-visible:ring-2 focus-visible:ring-ring">
            <Logo />
          </Link>
          {variant === 'admin' && (
            <Badge variant="warning" className="ml-auto gap-1">
              <Shield className="size-3" aria-hidden="true" />
              Admin
            </Badge>
          )}
        </div>
        {nav}
        <div className="border-t border-border p-3">
          <p className="px-3 text-[11px] leading-relaxed text-muted-foreground">
            Self-hosted · your keys never leave this server
          </p>
        </div>
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
          />
          <aside className="absolute left-0 top-0 flex h-full w-64 flex-col border-r border-border bg-card">
            <div className="flex h-16 items-center justify-between border-b border-border px-5">
              <Logo />
              <Button variant="ghost" size="icon-sm" onClick={() => setMobileOpen(false)} aria-label="Close navigation">
                <X aria-hidden="true" />
              </Button>
            </div>
            {nav}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border bg-background/85 px-4 backdrop-blur-md sm:px-6">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
          >
            <Menu aria-hidden="true" />
          </Button>
          <Link to={isAdmin ? '/admin' : '/app'} className="lg:hidden">
            <LogoMark className="size-7" />
          </Link>

          <div className="ml-auto flex items-center gap-1.5">
            <ThemeToggle />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="h-9 gap-2 px-2">
                  <span className="flex size-7 items-center justify-center rounded-full bg-primary/15 text-[11px] font-semibold text-primary">
                    {initials(user?.full_name ?? null, user?.email ?? '')}
                  </span>
                  <span className="hidden max-w-[10rem] truncate text-sm sm:block">
                    {user?.full_name || user?.email}
                  </span>
                  <ChevronDown className="size-3.5 opacity-60" aria-hidden="true" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel className="truncate normal-case">{user?.email}</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {isAdmin && (
                  <>
                    <DropdownMenuItem asChild>
                      <Link to={variant === 'admin' ? '/app' : '/admin'}>
                        {variant === 'admin' ? (
                          <>
                            <LayoutDashboard aria-hidden="true" /> My workspace
                          </>
                        ) : (
                          <>
                            <Shield aria-hidden="true" /> Admin panel
                          </>
                        )}
                      </Link>
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                  </>
                )}
                <DropdownMenuItem asChild>
                  <Link to="/app/settings">
                    <UserIcon aria-hidden="true" /> Profile
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link to="/app/settings?tab=keys">
                    <Settings aria-hidden="true" /> API keys
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem destructive onSelect={handleLogout}>
                  <LogOut aria-hidden="true" /> Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <main id="content" className="flex-1 px-4 py-6 sm:px-6 sm:py-8">
          <div className="mx-auto max-w-6xl">{children}</div>
        </main>
      </div>
    </div>
    </div>
  )
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: React.ReactNode
  actions?: React.ReactNode
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && (
          <p className="text-pretty text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
