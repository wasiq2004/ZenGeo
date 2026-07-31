import { KeyRound, ShieldAlert, ShieldCheck, User } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { PageHeader } from '@/components/layout/AppShell'
import { ApiKeysSection } from '@/components/settings/ApiKeysSection'
import { DangerZoneSection } from '@/components/settings/DangerZoneSection'
import { ProfileSection } from '@/components/settings/ProfileSection'
import { SecuritySection } from '@/components/settings/SecuritySection'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/misc'

const TABS = [
  { value: 'general', label: 'General', icon: User },
  { value: 'keys', label: 'API keys', icon: KeyRound },
  { value: 'security', label: 'Security', icon: ShieldCheck },
  { value: 'danger', label: 'Danger zone', icon: ShieldAlert },
] as const

export default function Settings() {
  // Tab lives in the URL so links like /app/settings?tab=keys work and the
  // browser back button behaves as expected.
  const [searchParams, setSearchParams] = useSearchParams()
  const requested = searchParams.get('tab')
  const active = TABS.some((t) => t.value === requested) ? requested! : 'general'

  return (
    <>
      <PageHeader
        title="Settings"
        description="Your profile, the AI providers you test against, and account security."
      />

      <Tabs
        value={active}
        onValueChange={(value) =>
          setSearchParams(value === 'general' ? {} : { tab: value }, { replace: true })
        }
      >
        <TabsList className="w-full justify-start overflow-x-auto sm:w-auto">
          {TABS.map((tab) => (
            <TabsTrigger key={tab.value} value={tab.value}>
              <tab.icon aria-hidden="true" />
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="general">
          <ProfileSection />
        </TabsContent>
        <TabsContent value="keys">
          <ApiKeysSection />
        </TabsContent>
        <TabsContent value="security">
          <SecuritySection />
        </TabsContent>
        <TabsContent value="danger">
          <DangerZoneSection />
        </TabsContent>
      </Tabs>
    </>
  )
}
