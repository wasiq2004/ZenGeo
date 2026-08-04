import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { ProtectedRoute, PublicOnlyRoute } from '@/components/ProtectedRoute'
import { LoadingScreen } from '@/components/ui/feedback'
import { TooltipProvider } from '@/components/ui/misc'
import { ToastProvider } from '@/components/ui/toast'
import { AuthProvider } from '@/lib/auth'
import { QueryProvider } from '@/lib/query'

// Route-level code splitting: the marketing page should not ship the charting
// library, and a signed-out visitor should not download the admin panel.
const Landing = lazy(() => import('@/pages/Landing'))
const PrivacyPolicy = lazy(() =>
  import('@/pages/Legal').then((m) => ({ default: m.PrivacyPolicy })),
)
const Terms = lazy(() => import('@/pages/Legal').then((m) => ({ default: m.Terms })))
const Login = lazy(() => import('@/pages/Login'))
const Signup = lazy(() => import('@/pages/Signup'))
const NotFound = lazy(() => import('@/pages/NotFound'))

const UserLayout = lazy(() => import('@/components/layout/UserLayout'))
const Dashboard = lazy(() => import('@/pages/app/Dashboard'))
const NewAudit = lazy(() => import('@/pages/app/NewAudit'))
const AuditDetail = lazy(() => import('@/pages/app/AuditDetail'))
const Reports = lazy(() => import('@/pages/app/Reports'))
const SettingsPage = lazy(() => import('@/pages/app/Settings'))

const AdminLayout = lazy(() => import('@/components/layout/AdminLayout'))
const AdminOverview = lazy(() => import('@/pages/admin/Overview'))
const AdminUsers = lazy(() => import('@/pages/admin/Users'))
const AdminUserDetail = lazy(() => import('@/pages/admin/UserDetail'))
const AdminAudits = lazy(() => import('@/pages/admin/Audits'))
const AdminActivity = lazy(() => import('@/pages/admin/Activity'))

// React Router 7 makes the former v7_* future flags the default behaviour, so
// they no longer need to be opted into on the router.
export default function App() {
  return (
    <BrowserRouter>
      <QueryProvider>
        <AuthProvider>
          <TooltipProvider delayDuration={200}>
            <ToastProvider>
              <Suspense fallback={<LoadingScreen />}>
                <Routes>
                  {/* Public */}
                  <Route path="/" element={<Landing />} />
                  <Route path="/privacy" element={<PrivacyPolicy />} />
                  <Route path="/terms" element={<Terms />} />
                  <Route
                    path="/login"
                    element={
                      <PublicOnlyRoute>
                        <Login />
                      </PublicOnlyRoute>
                    }
                  />
                  <Route
                    path="/signup"
                    element={
                      <PublicOnlyRoute>
                        <Signup />
                      </PublicOnlyRoute>
                    }
                  />

                  {/* User panel */}
                  <Route
                    path="/app"
                    element={
                      <ProtectedRoute>
                        <UserLayout />
                      </ProtectedRoute>
                    }
                  >
                    <Route index element={<Dashboard />} />
                    <Route path="audits/new" element={<NewAudit />} />
                    <Route path="audits/:auditId" element={<AuditDetail />} />
                    <Route path="reports" element={<Reports />} />
                    <Route path="settings" element={<SettingsPage />} />
                  </Route>

                  {/* Admin panel - also re-checked server-side on every request */}
                  <Route
                    path="/admin"
                    element={
                      <ProtectedRoute requireAdmin>
                        <AdminLayout />
                      </ProtectedRoute>
                    }
                  >
                    <Route index element={<AdminOverview />} />
                    <Route path="users" element={<AdminUsers />} />
                    <Route path="users/:userId" element={<AdminUserDetail />} />
                    <Route path="audits" element={<AdminAudits />} />
                    <Route path="activity" element={<AdminActivity />} />
                  </Route>

                  <Route path="/dashboard" element={<Navigate to="/app" replace />} />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
            </ToastProvider>
          </TooltipProvider>
        </AuthProvider>
      </QueryProvider>
    </BrowserRouter>
  )
}
