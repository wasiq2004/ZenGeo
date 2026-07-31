import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArrowLeft, ArrowRight, Check, Sparkles } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { PageHeader } from '@/components/layout/AppShell'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert } from '@/components/ui/feedback'
import { Field, Input, Label, Textarea } from '@/components/ui/input'
import { RadioGroup, RadioGroupItem, Switch } from '@/components/ui/misc'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { api, ApiError } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { PROVIDER_LABEL } from '@/lib/geo'
import type { Business, LLMApiKey } from '@/lib/types'
import { cn } from '@/lib/utils'

const schema = z.object({
  // A. Business identity
  name: z.string().min(1, 'Enter your business or brand name').max(200),
  industry: z.string().max(200).optional(),
  description: z.string().max(2000).optional(),
  targetAudience: z.string().max(2000).optional(),
  location: z.string().max(300).optional(),
  competitors: z.string().max(1000).optional(),
  uniqueSellingPoints: z.string().max(2000).optional(),
  // B. Website
  websiteUrl: z.string().min(1, 'Enter your website address').max(2000),
  keyPages: z.string().max(3000).optional(),
  cmsPlatform: z.string().max(120).optional(),
  controlsSiteRoot: z.boolean(),
  // C. Current AI presence
  checkedAiMentions: z.boolean(),
  hasWikipedia: z.enum(['yes', 'no', 'unsure']),
  publishesResearch: z.boolean(),
  updateFrequency: z.enum(['weekly', 'monthly', 'quarterly', 'rarely']),
  knownMentions: z.string().max(2000).optional(),
  // D. Target prompts
  targetPrompts: z.string().max(20000).optional(),
  // E. Goals
  goal: z.enum([
    'increase_visibility',
    'competitor_comparison',
    'health_check',
    'launch_preparation',
  ]),
  goalDetail: z.string().max(1000).optional(),
})

type FormValues = z.infer<typeof schema>

interface WizardStep {
  id: string
  title: string
  /** Validated before the step can be left. Later steps have no required fields. */
  fields: (keyof FormValues)[]
}

const STEPS: WizardStep[] = [
  { id: 'identity', title: 'Your business', fields: ['name'] },
  { id: 'website', title: 'Website', fields: ['websiteUrl'] },
  { id: 'presence', title: 'AI presence', fields: [] },
  { id: 'prompts', title: 'Target prompts', fields: [] },
  { id: 'goals', title: 'Goals', fields: [] },
]

const GOALS = [
  { value: 'increase_visibility', label: 'Increase AI visibility', hint: 'Get named more often in AI answers' },
  { value: 'competitor_comparison', label: 'Compare against competitors', hint: 'See who assistants recommend instead' },
  { value: 'health_check', label: 'General health check', hint: 'Find out where you stand today' },
  { value: 'launch_preparation', label: 'Prepare for a launch', hint: 'Get the groundwork right before you ship' },
] as const

function toLines(value: string | undefined): string[] {
  return (value ?? '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

export default function NewAudit() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [step, setStep] = useState(0)
  const [formError, setFormError] = useState<string | null>(null)
  const [existingId, setExistingId] = useState<string>('')

  const businessesQuery = useQuery({
    queryKey: ['businesses'],
    queryFn: () => api.get<Business[]>('/businesses'),
  })
  const keysQuery = useQuery({
    queryKey: ['llm-keys'],
    queryFn: () => api.get<LLMApiKey[]>('/llm-keys'),
  })

  const activeProviders = useMemo(
    () => [...new Set((keysQuery.data ?? []).filter((k) => k.is_active).map((k) => k.provider))],
    [keysQuery.data],
  )

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    mode: 'onBlur',
    defaultValues: {
      name: '',
      websiteUrl: '',
      controlsSiteRoot: true,
      checkedAiMentions: false,
      hasWikipedia: 'unsure',
      publishesResearch: false,
      updateFrequency: 'monthly',
      goal: 'health_check',
      targetPrompts: '',
    },
  })

  const prompts = toLines(form.watch('targetPrompts'))
  const plannedCalls = prompts.length * activeProviders.length

  const startAudit = useMutation({
    mutationFn: (values: FormValues) =>
      api.post<{ audit: { id: string }; message: string }>('/audits', {
        ...(existingId ? { business_id: existingId } : {}),
        business: {
          name: values.name,
          website_url: values.websiteUrl,
          industry: values.industry || null,
          description: values.description || null,
          target_audience: values.targetAudience || null,
          location: values.location || null,
          competitors: toLines(values.competitors?.replace(/,/g, '\n')),
          unique_selling_points: values.uniqueSellingPoints || null,
          key_pages: toLines(values.keyPages),
          cms_platform: values.cmsPlatform || null,
        },
        questionnaire: {
          ai_presence: {
            checked_ai_mentions: values.checkedAiMentions,
            has_wikipedia_or_wikidata: values.hasWikipedia,
            publishes_original_research: values.publishesResearch,
            content_update_frequency: values.updateFrequency,
            known_third_party_mentions: values.knownMentions || null,
          },
          target_prompts: toLines(values.targetPrompts),
          goal: values.goal,
          goal_detail: values.goalDetail || null,
          controls_site_root: values.controlsSiteRoot,
        },
      }),
    onSuccess: (data) => navigate(`/app/audits/${data.audit.id}`),
    onError: (error) =>
      setFormError(
        error instanceof ApiError ? error.message : 'Could not start the audit. Try again.',
      ),
  })

  const prefill = (businessId: string) => {
    setExistingId(businessId)
    const business = businessesQuery.data?.find((b) => b.id === businessId)
    if (!business) return
    form.reset({
      ...form.getValues(),
      name: business.name,
      websiteUrl: business.website_url,
      industry: business.industry ?? '',
      description: business.description ?? '',
      targetAudience: business.target_audience ?? '',
      location: business.location ?? '',
      competitors: (business.competitors ?? []).join('\n'),
      uniqueSellingPoints: business.unique_selling_points ?? '',
      keyPages: (business.key_pages ?? []).join('\n'),
      cmsPlatform: business.cms_platform ?? '',
    })
  }

  const next = async () => {
    const fields = STEPS[step]?.fields ?? []
    if (fields.length > 0 && !(await form.trigger(fields))) return
    setStep((s) => Math.min(s + 1, STEPS.length - 1))
  }

  const isLast = step === STEPS.length - 1

  if (user && !user.is_email_verified) {
    return (
      <>
        <PageHeader title="Run an audit" />
        <Alert variant="warning" title="Confirm your email first">
          Audits run against real websites and can spend credit on your own API keys, so we ask
          you to confirm your address before the first one.{' '}
          <Link to="/app/settings" className="font-medium">
            Send a new confirmation link
          </Link>
          .
        </Alert>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="Run an audit"
        description="Tell us about your business, then we scan your site and test the assistants."
      />

      {/* Step indicator doubles as the progress readout. */}
      <ol className="mb-6 flex flex-wrap items-center gap-2" aria-label="Audit setup steps">
        {STEPS.map((s, index) => (
          <li key={s.id} className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => index < step && setStep(index)}
              disabled={index > step}
              aria-current={index === step ? 'step' : undefined}
              className={cn(
                'flex items-center gap-2 rounded-full px-3 py-1.5 text-sm transition-colors',
                index === step && 'bg-primary/12 font-medium text-primary',
                index < step && 'text-muted-foreground hover:text-foreground',
                index > step && 'cursor-not-allowed text-muted-foreground/60',
              )}
            >
              <span
                className={cn(
                  'flex size-5 items-center justify-center rounded-full text-[11px]',
                  index < step ? 'bg-success text-success-foreground' : 'bg-muted',
                )}
              >
                {index < step ? <Check className="size-3" aria-hidden="true" /> : index + 1}
              </span>
              {s.title}
            </button>
            {index < STEPS.length - 1 && (
              <span className="hidden h-px w-4 bg-border sm:block" aria-hidden="true" />
            )}
          </li>
        ))}
      </ol>

      <form
        onSubmit={form.handleSubmit((v) => startAudit.mutate(v))}
        noValidate
        className="space-y-6"
      >
        {formError && <Alert variant="error">{formError}</Alert>}

        {step === 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Your business</CardTitle>
              <CardDescription>
                This is what we look for in AI answers, so use the name customers would say.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {(businessesQuery.data?.length ?? 0) > 0 && (
                <Field label="Start from a saved business" hint="Or leave blank to add a new one">
                  {(props) => (
                    <Select value={existingId} onValueChange={prefill}>
                      <SelectTrigger id={props.id}>
                        <SelectValue placeholder="New business" />
                      </SelectTrigger>
                      <SelectContent>
                        {businessesQuery.data?.map((business) => (
                          <SelectItem key={business.id} value={business.id}>
                            {business.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                </Field>
              )}

              <Field label="Business or brand name" error={form.formState.errors.name?.message} required>
                {(props) => <Input {...props} {...form.register('name')} placeholder="Acme Analytics" />}
              </Field>

              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Industry or category">
                  {(props) => (
                    <Input {...props} {...form.register('industry')} placeholder="B2B SaaS analytics" />
                  )}
                </Field>
                <Field label="Service area or location">
                  {(props) => (
                    <Input {...props} {...form.register('location')} placeholder="United Kingdom" />
                  )}
                </Field>
              </div>

              <Field label="One line on what you do">
                {(props) => (
                  <Textarea
                    {...props}
                    {...form.register('description')}
                    rows={2}
                    placeholder="Product analytics for small engineering teams."
                  />
                )}
              </Field>

              <Field label="Who is it for?">
                {(props) => (
                  <Textarea
                    {...props}
                    {...form.register('targetAudience')}
                    rows={2}
                    placeholder="Engineering leads at 10-50 person startups."
                  />
                )}
              </Field>

              <Field
                label="Top competitors"
                hint="One per line. We check whether assistants name them instead of you."
              >
                {(props) => (
                  <Textarea
                    {...props}
                    {...form.register('competitors')}
                    rows={3}
                    placeholder={'Mixpanel\nAmplitude\nPostHog'}
                  />
                )}
              </Field>

              <Field label="What makes you different?">
                {(props) => (
                  <Textarea
                    {...props}
                    {...form.register('uniqueSellingPoints')}
                    rows={2}
                    placeholder="The only one with per-commit attribution."
                  />
                )}
              </Field>
            </CardContent>
          </Card>
        )}

        {step === 1 && (
          <Card>
            <CardHeader>
              <CardTitle>Website</CardTitle>
              <CardDescription>What we crawl and score.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field
                label="Website address"
                hint="We only fetch public pages, over http or https"
                error={form.formState.errors.websiteUrl?.message}
                required
              >
                {(props) => (
                  <Input
                    {...props}
                    {...form.register('websiteUrl')}
                    inputMode="url"
                    placeholder="https://acme.com"
                  />
                )}
              </Field>

              <Field
                label="Most important pages"
                hint="One URL per line. Leave blank and we follow your main navigation instead."
              >
                {(props) => (
                  <Textarea
                    {...props}
                    {...form.register('keyPages')}
                    rows={4}
                    placeholder={'https://acme.com/product\nhttps://acme.com/pricing\nhttps://acme.com/about'}
                  />
                )}
              </Field>

              <Field label="CMS or platform" hint="Optional — helps us word the fixes for your stack">
                {(props) => (
                  <Input {...props} {...form.register('cmsPlatform')} placeholder="WordPress, Webflow, Next.js…" />
                )}
              </Field>

              <div className="flex items-start justify-between gap-4 rounded-lg border border-border p-4">
                <div className="space-y-0.5">
                  <Label htmlFor="controls-root">I can add files to the site root</Label>
                  <p className="text-sm text-muted-foreground">
                    Whether you can publish robots.txt and llms.txt yourself. If not, we still show
                    that advice but flag who needs to action it.
                  </p>
                </div>
                <Switch
                  id="controls-root"
                  checked={form.watch('controlsSiteRoot')}
                  onCheckedChange={(v) => form.setValue('controlsSiteRoot', v)}
                />
              </div>
            </CardContent>
          </Card>
        )}

        {step === 2 && (
          <Card>
            <CardHeader>
              <CardTitle>Current AI presence</CardTitle>
              <CardDescription>
                Context the crawler cannot work out on its own.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="flex items-center justify-between gap-4 rounded-lg border border-border p-4">
                <Label htmlFor="checked-mentions">
                  Have you checked whether assistants mention you?
                </Label>
                <Switch
                  id="checked-mentions"
                  checked={form.watch('checkedAiMentions')}
                  onCheckedChange={(v) => form.setValue('checkedAiMentions', v)}
                />
              </div>

              <Field label="Do you have a Wikipedia or Wikidata entry?">
                {(props) => (
                  <RadioGroup
                    id={props.id}
                    value={form.watch('hasWikipedia')}
                    onValueChange={(v) => form.setValue('hasWikipedia', v as 'yes' | 'no' | 'unsure')}
                    className="flex gap-4"
                  >
                    {(['yes', 'no', 'unsure'] as const).map((option) => (
                      <label key={option} className="flex cursor-pointer items-center gap-2 text-sm capitalize">
                        <RadioGroupItem value={option} /> {option}
                      </label>
                    ))}
                  </RadioGroup>
                )}
              </Field>

              <div className="flex items-center justify-between gap-4 rounded-lg border border-border p-4">
                <Label htmlFor="publishes-research">
                  Do you publish original research, data or statistics?
                </Label>
                <Switch
                  id="publishes-research"
                  checked={form.watch('publishesResearch')}
                  onCheckedChange={(v) => form.setValue('publishesResearch', v)}
                />
              </div>

              <Field label="How often is your content updated?">
                {(props) => (
                  <Select
                    value={form.watch('updateFrequency')}
                    onValueChange={(v) =>
                      form.setValue('updateFrequency', v as FormValues['updateFrequency'])
                    }
                  >
                    <SelectTrigger id={props.id}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="weekly">Weekly</SelectItem>
                      <SelectItem value="monthly">Monthly</SelectItem>
                      <SelectItem value="quarterly">Quarterly</SelectItem>
                      <SelectItem value="rarely">Rarely</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              </Field>

              <Field
                label="Third-party coverage you know about"
                hint="Directories, press, podcasts, review sites — anywhere you are already mentioned"
              >
                {(props) => (
                  <Textarea
                    {...props}
                    {...form.register('knownMentions')}
                    rows={3}
                    placeholder="Featured in TechCrunch (2025), listed on G2 and Capterra…"
                  />
                )}
              </Field>
            </CardContent>
          </Card>
        )}

        {step === 3 && (
          <Card>
            <CardHeader>
              <CardTitle>Target prompts</CardTitle>
              <CardDescription>
                The questions a prospective customer might actually ask an AI assistant. We send
                each one to every provider you have connected and check whether you show up.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {activeProviders.length === 0 ? (
                <Alert variant="warning" title="No AI provider connected">
                  Without a key, Share of Voice is skipped and its 15% weight is spread across the
                  other six pillars — your score stays on the same 0–100 scale.{' '}
                  <Link to="/app/settings?tab=keys" className="font-medium">
                    Connect a key
                  </Link>{' '}
                  to unlock live testing.
                </Alert>
              ) : (
                <Alert variant="info" title="Testing against your own keys">
                  <div className="flex flex-wrap items-center gap-1.5 pt-1">
                    {activeProviders.map((provider) => (
                      <Badge key={provider} variant="secondary">
                        {PROVIDER_LABEL[provider] ?? provider}
                      </Badge>
                    ))}
                  </div>
                </Alert>
              )}

              <Field
                label="Your target prompts"
                hint="One per line. There is no limit — the cost lands on your own key, so it is your call."
              >
                {(props) => (
                  <Textarea
                    {...props}
                    {...form.register('targetPrompts')}
                    rows={8}
                    placeholder={
                      'best project management tool for small agencies in Bangalore\nwhat analytics tools work well for early stage startups\nalternatives to Mixpanel for small teams'
                    }
                  />
                )}
              </Field>

              {prompts.length > 0 && activeProviders.length > 0 && (
                <div className="rounded-lg border border-border bg-muted/40 p-4 text-sm">
                  <p className="font-medium">
                    {prompts.length} prompt{prompts.length === 1 ? '' : 's'} ×{' '}
                    {activeProviders.length} provider{activeProviders.length === 1 ? '' : 's'} ={' '}
                    <span className="tabular-nums">{plannedCalls}</span> API call
                    {plannedCalls === 1 ? '' : 's'}
                  </p>
                  <p className="mt-1 text-muted-foreground">
                    Billed to your own provider accounts. We queue them at a safe rate so no
                    provider throttles you.
                  </p>
                  {plannedCalls > 100 && (
                    <p className="mt-2 flex items-start gap-1.5 text-warning">
                      <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                      That is a large run. It will take a while and cost accordingly — no limit is
                      imposed, we just want it to be visible before you start.
                    </p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {step === 4 && (
          <Card>
            <CardHeader>
              <CardTitle>What is this audit for?</CardTitle>
              <CardDescription>Shapes how we prioritise the recommendations.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <RadioGroup
                value={form.watch('goal')}
                onValueChange={(v) => form.setValue('goal', v as FormValues['goal'])}
                className="grid gap-3 sm:grid-cols-2"
              >
                {GOALS.map((goal) => (
                  <label
                    key={goal.value}
                    className={cn(
                      'flex cursor-pointer items-start gap-3 rounded-lg border p-4 transition-colors',
                      form.watch('goal') === goal.value
                        ? 'border-primary bg-primary/5'
                        : 'border-border hover:border-primary/40',
                    )}
                  >
                    <RadioGroupItem value={goal.value} className="mt-0.5" />
                    <span className="space-y-0.5">
                      <span className="block text-sm font-medium">{goal.label}</span>
                      <span className="block text-xs text-muted-foreground">{goal.hint}</span>
                    </span>
                  </label>
                ))}
              </RadioGroup>

              <Field label="Anything else we should know?">
                {(props) => (
                  <Textarea
                    {...props}
                    {...form.register('goalDetail')}
                    rows={3}
                    placeholder="We are launching a new pricing page next month."
                  />
                )}
              </Field>

              <div className="rounded-lg border border-border p-4 text-sm">
                <p className="mb-2 font-medium">Ready to run</p>
                <dl className="grid gap-1 text-muted-foreground sm:grid-cols-2">
                  <div>
                    <dt className="inline">Business: </dt>
                    <dd className="inline text-foreground">{form.watch('name') || '—'}</dd>
                  </div>
                  <div>
                    <dt className="inline">Website: </dt>
                    <dd className="inline text-foreground">{form.watch('websiteUrl') || '—'}</dd>
                  </div>
                  <div>
                    <dt className="inline">Target prompts: </dt>
                    <dd className="inline text-foreground">{prompts.length}</dd>
                  </div>
                  <div>
                    <dt className="inline">Planned API calls: </dt>
                    <dd className="inline text-foreground tabular-nums">{plannedCalls}</dd>
                  </div>
                </dl>
              </div>
            </CardContent>
          </Card>
        )}

        <div className="flex items-center justify-between gap-3">
          <Button
            type="button"
            variant="outline"
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0}
          >
            <ArrowLeft aria-hidden="true" /> Back
          </Button>

          {isLast ? (
            <Button type="submit" loading={startAudit.isPending}>
              <Sparkles aria-hidden="true" /> Start the audit
            </Button>
          ) : (
            <Button type="button" onClick={next}>
              Continue <ArrowRight aria-hidden="true" />
            </Button>
          )}
        </div>
      </form>
    </>
  )
}
