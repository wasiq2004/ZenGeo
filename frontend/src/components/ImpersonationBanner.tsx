import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShieldAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth'

/**
 * Persistent "you are not yourself" banner.
 *
 * Rendered above everything, on every authenticated screen, for as long as an
 * admin is acting as another user. It is deliberately loud and cannot be
 * dismissed: the danger of impersonation is forgetting you are in it and
 * reading someone else's data as though it were your own dashboard.
 *
 * The banner is a reminder, not a control. Account-destructive actions are
 * refused by the API itself (deps.forbid_impersonation), so hiding or faking
 * this component changes nothing about what the session may do.
 */
export function ImpersonationBanner() {
  const { user, impersonatedBy, endImpersonation } = useAuth()
  const [leaving, setLeaving] = useState(false)
  const navigate = useNavigate()

  if (!impersonatedBy || !user) return null

  const leave = async () => {
    setLeaving(true)
    try {
      await endImpersonation()
      navigate('/admin/users', { replace: true })
    } finally {
      setLeaving(false)
    }
  }

  return (
    <div
      role="status"
      className="sticky top-0 z-50 flex flex-wrap items-center justify-center gap-x-3 gap-y-1
                 border-b border-warning/40 bg-warning/15 px-4 py-2 text-sm backdrop-blur"
    >
      <ShieldAlert aria-hidden="true" className="size-4 shrink-0 text-warning" />
      <span>
        Viewing as <strong>{user.full_name || user.email}</strong> — admin mode. Account changes are
        blocked, and this session ends automatically after 30 minutes.
      </span>
      <Button size="sm" variant="outline" loading={leaving} onClick={leave}>
        Return to admin
      </Button>
    </div>
  )
}
