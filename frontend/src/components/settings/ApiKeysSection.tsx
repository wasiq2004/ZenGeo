import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle2,
  ExternalLink,
  Globe,
  KeyRound,
  Lock,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Alert, EmptyState, Skeleton } from '@/components/ui/feedback'
import { Field, Input, Label } from '@/components/ui/input'
import { Switch, Tooltip } from '@/components/ui/misc'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/toast'
import { api, ApiError } from '@/lib/api'
import { formatRelative } from '@/lib/format'
import type { LLMApiKey, ProviderInfo, ProviderName } from '@/lib/types'

const keySchema = z.object({
  provider: z.string().min(1, 'Choose a provider'),
  apiKey: z.string().min(8, 'That key looks too short'),
  label: z.string().min(1, 'Give this key a label').max(100),
  model: z.string().max(120).optional(),
  useWebSearch: z.boolean(),
})

type KeyFormValues = z.infer<typeof keySchema>

interface CreateResponse {
  key: LLMApiKey
  validation: { ok: boolean; message: string; available_models: string[] } | null
}

function AddKeyDialog({ providers }: { providers: ProviderInfo[] }) {
  const [open, setOpen] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const form = useForm<KeyFormValues>({
    resolver: zodResolver(keySchema),
    defaultValues: {
      provider: providers[0]?.name ?? 'openai',
      label: 'default',
      model: '',
      useWebSearch: true,
      apiKey: '',
    },
  })

  const providerName = form.watch('provider')
  const selected = providers.find((p) => p.name === providerName)

  const createKey = useMutation({
    mutationFn: (values: KeyFormValues) =>
      api.post<CreateResponse>('/llm-keys', {
        provider: values.provider,
        api_key: values.apiKey,
        label: values.label,
        model: values.model?.trim() || null,
        use_web_search: values.useWebSearch,
        validate_before_save: true,
      }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['llm-keys'] })
      setOpen(false)
      form.reset()
      setFormError(null)
      toast({
        title: 'Key connected',
        description: data.validation?.message ?? 'Ready to use in your next audit.',
        variant: 'success',
      })
    },
    onError: (error) =>
      setFormError(
        error instanceof ApiError ? error.message : 'Could not reach the server. Try again.',
      ),
  })

  return (
    <>
      <Button onClick={() => setOpen(true)}>
        <Plus aria-hidden="true" /> Connect a key
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Connect an API key</DialogTitle>
            <DialogDescription>
              We verify the key with the provider before saving it, then encrypt it. You will never
              see it again — only a masked preview.
            </DialogDescription>
          </DialogHeader>

          <form
            onSubmit={form.handleSubmit((v) => createKey.mutate(v))}
            className="space-y-4"
            noValidate
          >
            {formError && <Alert variant="error">{formError}</Alert>}

            <Field label="Provider" required>
              {(props) => (
                <Select
                  value={providerName}
                  onValueChange={(value) => {
                    form.setValue('provider', value)
                    form.setValue('model', '')
                  }}
                >
                  <SelectTrigger id={props.id} aria-describedby={props['aria-describedby']}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {providers.map((provider) => (
                      <SelectItem key={provider.name} value={provider.name}>
                        {provider.display_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </Field>

            <Field
              label="API key"
              hint={selected?.key_format_hint}
              error={form.formState.errors.apiKey?.message}
              required
            >
              {(props) => (
                <Input
                  {...props}
                  {...form.register('apiKey')}
                  type="password"
                  autoComplete="off"
                  spellCheck={false}
                  placeholder="Paste your key"
                />
              )}
            </Field>

            {selected?.docs_url && (
              <a
                href={selected.docs_url}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
              >
                Get a key from {selected.display_name}
                <ExternalLink className="size-3" aria-hidden="true" />
              </a>
            )}

            <Field
              label="Label"
              hint="Lets you tell two keys for the same provider apart"
              error={form.formState.errors.label?.message}
              required
            >
              {(props) => <Input {...props} {...form.register('label')} placeholder="default" />}
            </Field>

            <Field
              label="Model"
              hint={`Leave blank for ${selected?.default_model ?? 'the default'}. Any model your key can reach works.`}
              error={form.formState.errors.model?.message}
            >
              {(props) => (
                <Input
                  {...props}
                  {...form.register('model')}
                  list="model-suggestions"
                  placeholder={selected?.default_model}
                />
              )}
            </Field>
            <datalist id="model-suggestions">
              {selected?.models.map((model) => (
                <option key={model} value={model} />
              ))}
            </datalist>

            {selected?.supports_web_search && !selected.always_grounded && (
              <div className="flex items-start justify-between gap-4 rounded-lg border border-border p-3">
                <div className="space-y-0.5">
                  <Label htmlFor="use-web-search">Answer with live web search</Label>
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    Makes citation rates comparable with Perplexity. Costs more per prompt on your
                    account.
                  </p>
                </div>
                <Switch
                  id="use-web-search"
                  checked={form.watch('useWebSearch')}
                  onCheckedChange={(checked) => form.setValue('useWebSearch', checked)}
                />
              </div>
            )}

            {selected?.always_grounded && (
              <Alert variant="info">
                {selected.display_name} always answers from live web results, so its answers are
                grounded by default.
              </Alert>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={createKey.isPending}>
                Verify and save
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}

function KeyRow({ apiKey, provider }: { apiKey: LLMApiKey; provider?: ProviderInfo }) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [confirmDelete, setConfirmDelete] = useState(false)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['llm-keys'] })

  const revalidate = useMutation({
    mutationFn: () => api.post<{ ok: boolean; message: string }>(`/llm-keys/${apiKey.id}/validate`),
    onSuccess: (result) => {
      invalidate()
      toast({
        title: result.ok ? 'Key still works' : 'Key check failed',
        description: result.message,
        variant: result.ok ? 'success' : 'error',
      })
    },
    onError: (error) =>
      toast({
        title: 'Key check failed',
        description: error instanceof ApiError ? error.message : undefined,
        variant: 'error',
      }),
  })

  const toggleActive = useMutation({
    mutationFn: (isActive: boolean) => api.patch(`/llm-keys/${apiKey.id}`, { is_active: isActive }),
    onSuccess: invalidate,
    onError: () => toast({ title: 'Could not update the key', variant: 'error' }),
  })

  const remove = useMutation({
    mutationFn: () => api.delete(`/llm-keys/${apiKey.id}`),
    onSuccess: () => {
      invalidate()
      setConfirmDelete(false)
      toast({ title: 'Key deleted', description: 'Removed from the database entirely.' })
    },
    onError: () => toast({ title: 'Could not delete the key', variant: 'error' }),
  })

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{provider?.display_name ?? apiKey.provider}</span>
          <Badge variant="secondary">{apiKey.label}</Badge>
          {!apiKey.is_active && <Badge variant="muted">Paused</Badge>}
          {apiKey.use_web_search && provider?.supports_web_search && (
            <Tooltip content="Answers are backed by live web search, so citations are comparable across providers.">
              <Badge variant="outline" className="gap-1">
                <Globe aria-hidden="true" /> Grounded
              </Badge>
            </Tooltip>
          )}
        </div>
        <p className="font-mono text-xs text-muted-foreground">{apiKey.key_preview}</p>
        <p className="text-xs text-muted-foreground">
          {apiKey.model ?? provider?.default_model ?? 'default model'} ·{' '}
          {apiKey.last_validated_at
            ? `verified ${formatRelative(apiKey.last_validated_at)}`
            : 'not verified yet'}
          {apiKey.last_used_at ? ` · last used ${formatRelative(apiKey.last_used_at)}` : ''}
        </p>
      </div>

      <div className="flex shrink-0 items-center gap-1.5">
        <Tooltip content={apiKey.is_active ? 'Pause this key' : 'Use this key again'}>
          <span>
            <Switch
              checked={apiKey.is_active}
              onCheckedChange={(checked) => toggleActive.mutate(checked)}
              disabled={toggleActive.isPending}
              aria-label={apiKey.is_active ? 'Pause this key' : 'Activate this key'}
            />
          </span>
        </Tooltip>
        <Tooltip content="Re-check with the provider">
          <Button
            variant="ghost"
            size="icon-sm"
            loading={revalidate.isPending}
            onClick={() => revalidate.mutate()}
            aria-label="Re-check this key"
          >
            <RefreshCw aria-hidden="true" />
          </Button>
        </Tooltip>
        <Tooltip content="Delete permanently">
          <Button
            variant="ghost"
            size="icon-sm"
            className="text-destructive hover:bg-destructive/10"
            onClick={() => setConfirmDelete(true)}
            aria-label="Delete this key"
          >
            <Trash2 aria-hidden="true" />
          </Button>
        </Tooltip>
      </div>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete this API key?"
        description={
          <>
            The <span className="font-medium text-foreground">{apiKey.key_preview}</span> key for{' '}
            {provider?.display_name ?? apiKey.provider} will be removed from the database entirely.
            Audits already run keep their results, but future audits will skip this provider.
          </>
        }
        confirmLabel="Delete key"
        destructive
        loading={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </div>
  )
}

export function ApiKeysSection() {
  const providersQuery = useQuery({
    queryKey: ['llm-providers'],
    queryFn: () => api.get<ProviderInfo[]>('/llm-keys/providers'),
    staleTime: 10 * 60_000,
  })

  const keysQuery = useQuery({
    queryKey: ['llm-keys'],
    queryFn: () => api.get<LLMApiKey[]>('/llm-keys'),
  })

  const providers = providersQuery.data ?? []
  const keys = keysQuery.data ?? []
  const byName = (name: ProviderName) => providers.find((p) => p.name === name)

  return (
    <div className="space-y-6">
      <Alert variant="info" icon={Lock} title="How your keys are handled">
        <ul className="mt-1 list-inside list-disc space-y-1">
          <li>Encrypted before they touch the database, decrypted only in memory for your audit.</li>
          <li>Never written to logs, never returned to the browser, never visible to admins.</li>
          <li>
            No cap on how many prompts or providers you test — the cost lands on your own account,
            so it is your call.
          </li>
        </ul>
      </Alert>

      <Card>
        <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
          <div className="space-y-1">
            <CardTitle>Connected keys</CardTitle>
            <CardDescription>
              Every connected provider is tested during the Share of Voice pillar.
            </CardDescription>
          </div>
          {providers.length > 0 && <AddKeyDialog providers={providers} />}
        </CardHeader>
        <CardContent className="space-y-3">
          {keysQuery.isLoading ? (
            <>
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
            </>
          ) : keys.length === 0 ? (
            <EmptyState
              icon={KeyRound}
              title="No keys connected yet"
              description="Without a key the other six pillars still produce a full score — the Share of Voice pillar is skipped and its weight is redistributed."
              action={providers.length > 0 ? <AddKeyDialog providers={providers} /> : undefined}
            />
          ) : (
            keys.map((key) => (
              <KeyRow key={key.id} apiKey={key} provider={byName(key.provider)} />
            ))
          )}
        </CardContent>
      </Card>

      {keys.some((key) => key.is_active) && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <CheckCircle2 className="size-4 text-success" aria-hidden="true" />
          Share of Voice is unlocked. Your next audit will test all seven pillars.
        </p>
      )}
    </div>
  )
}
