import { Link } from 'react-router-dom'
import { Logo } from '@/components/Logo'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth'

export default function NotFound() {
  const { isAuthenticated, isAdmin } = useAuth()
  const home = !isAuthenticated ? '/' : isAdmin ? '/admin' : '/app'

  return (
    <div className="glow-surface flex min-h-screen flex-col items-center justify-center gap-6 px-6 text-center">
      <Logo />
      <div className="space-y-2">
        <p className="text-6xl font-semibold tracking-tight text-muted-foreground/40">404</p>
        <h1 className="text-xl font-semibold">This page does not exist</h1>
        <p className="max-w-sm text-sm text-muted-foreground">
          The link may be out of date, or the page may have moved.
        </p>
      </div>
      <Button asChild>
        <Link to={home}>Go back</Link>
      </Button>
    </div>
  )
}
