import { useMutation } from '@tanstack/react-query'
import { Download, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert } from '@/components/ui/feedback'
import { Field, Input } from '@/components/ui/input'
import { useToast } from '@/components/ui/toast'
import { api, ApiError, apiDownload } from '@/lib/api'
import { useAuth } from '@/lib/auth'

const CONFIRMATION = 'DELETE'

export function DangerZoneSection() {
  const { logout } = useAuth()
  const { toast } = useToast()
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState<string | null>(null)

  const exportData = useMutation({
    mutationFn: async () => {
      const blob = await apiDownload('/users/me/export')
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `checkgeo-export-${new Date().toISOString().slice(0, 10)}.json`
      link.click()
      URL.revokeObjectURL(url)
    },
    onSuccess: () => toast({ title: 'Export downloaded', variant: 'success' }),
    onError: () => toast({ title: 'Could not build the export', variant: 'error' }),
  })

  const deleteAccount = useMutation({
    mutationFn: () => api.post('/users/me/delete', { password, confirmation }),
    onSuccess: async () => {
      await logout()
      navigate('/', { replace: true })
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : 'Could not delete the account.'),
  })

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Export your data</CardTitle>
          <CardDescription>
            Everything we hold about you as JSON: profile, businesses, audits and results. API keys
            are listed by provider and preview only — the keys themselves are never exported.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline" loading={exportData.isPending} onClick={() => exportData.mutate()}>
            <Download aria-hidden="true" /> Download my data
          </Button>
        </CardContent>
      </Card>

      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <TriangleAlert className="size-4.5" aria-hidden="true" />
            Delete your account
          </CardTitle>
          <CardDescription>
            Permanently removes your profile, businesses, audits, reports and stored API keys. This
            cannot be undone — export your data first if you want a copy.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              deleteAccount.mutate()
            }}
            className="max-w-sm space-y-4"
            noValidate
          >
            {error && <Alert variant="error">{error}</Alert>}

            <Field label="Password" required>
              {(props) => (
                <Input
                  {...props}
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              )}
            </Field>

            <Field label={`Type ${CONFIRMATION} to confirm`} required>
              {(props) => (
                <Input
                  {...props}
                  value={confirmation}
                  onChange={(e) => setConfirmation(e.target.value)}
                  placeholder={CONFIRMATION}
                  autoComplete="off"
                />
              )}
            </Field>

            <Button
              type="submit"
              variant="destructive"
              loading={deleteAccount.isPending}
              disabled={!password || confirmation !== CONFIRMATION}
            >
              Delete my account permanently
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
