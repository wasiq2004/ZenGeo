import { FileBarChart, LayoutDashboard, Settings, Sparkles } from 'lucide-react'
import { Outlet } from 'react-router-dom'
import { AppShell, type NavItem } from './AppShell'

const items: NavItem[] = [
  { to: '/app', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/app/audits/new', label: 'Run an audit', icon: Sparkles },
  { to: '/app/reports', label: 'Reports', icon: FileBarChart },
  { to: '/app/settings', label: 'Settings', icon: Settings },
]

export default function UserLayout() {
  return (
    <AppShell items={items} variant="user">
      <Outlet />
    </AppShell>
  )
}
