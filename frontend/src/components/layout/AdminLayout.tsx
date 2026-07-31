import { ClipboardList, Gauge, ScrollText, Users } from 'lucide-react'
import { Outlet } from 'react-router-dom'
import { AppShell, type NavItem } from './AppShell'

const items: NavItem[] = [
  { to: '/admin', label: 'Overview', icon: Gauge, end: true },
  { to: '/admin/users', label: 'Users', icon: Users },
  { to: '/admin/audits', label: 'Audits', icon: ClipboardList },
  { to: '/admin/activity', label: 'Activity log', icon: ScrollText },
]

export default function AdminLayout() {
  return (
    <AppShell items={items} variant="admin">
      <Outlet />
    </AppShell>
  )
}
