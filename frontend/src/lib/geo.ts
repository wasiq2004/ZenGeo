/**
 * GEO scoring vocabulary shared across the UI.
 *
 * Keys and weights mirror `backend/app/audit/pillars/__init__.py` - the backend
 * is authoritative, this file exists so the UI can label and colour results
 * without a round trip.
 */
import type { AuditStatus, Effort, Impact } from './types'

export interface PillarMeta {
  key: string
  name: string
  shortName: string
  weight: number
  description: string
}

export const PILLARS: PillarMeta[] = [
  {
    key: 'crawlability',
    name: 'Crawlability & AI Bot Access',
    shortName: 'Crawlability',
    weight: 0.15,
    description:
      'Whether AI crawlers such as GPTBot, ClaudeBot and PerplexityBot are allowed to reach your pages at all, and whether those pages return real content without JavaScript.',
  },
  {
    key: 'llms_txt',
    name: 'llms.txt Brand File',
    shortName: 'llms.txt',
    weight: 0.1,
    description:
      'A purpose-built, machine-readable file at your site root that tells an AI assistant who you are and which pages matter.',
  },
  {
    key: 'structured_data',
    name: 'Structured Data',
    shortName: 'Schema',
    weight: 0.15,
    description:
      'Schema.org JSON-LD that states your entity facts — organisation, products, FAQs — in a form a model can parse without guessing.',
  },
  {
    key: 'extractability',
    name: 'Content Extractability',
    shortName: 'Extractability',
    weight: 0.2,
    description:
      'How easily a model can lift a clean, quotable answer out of your pages: heading hierarchy, direct answers up front, lists and tables.',
  },
  {
    key: 'evidence',
    name: 'Evidence & E-E-A-T',
    shortName: 'Evidence',
    weight: 0.15,
    description:
      'Citations, statistics, named sources, bylines and fresh dates — the signals that make a claim safe for a model to repeat.',
  },
  {
    key: 'entity_authority',
    name: 'Entity Authority',
    shortName: 'Authority',
    weight: 0.1,
    description:
      'Whether you exist as a recognised entity: Wikipedia/Wikidata presence, sameAs links to established profiles, and consistent contact details.',
  },
  {
    key: 'share_of_voice',
    name: 'AI Share of Voice',
    shortName: 'Share of Voice',
    weight: 0.15,
    description:
      'Live testing: your own target prompts are sent to the AI assistants you have connected, and the answers are checked for mentions, citations and competitors.',
  },
]

export const PILLAR_BY_KEY = Object.fromEntries(PILLARS.map((p) => [p.key, p])) as Record<
  string,
  PillarMeta
>

export type ScoreBand = 'Poor' | 'Needs Work' | 'Good' | 'Excellent'

export function scoreBand(score: number | null | undefined): ScoreBand {
  if (score == null) return 'Poor'
  if (score >= 80) return 'Excellent'
  if (score >= 60) return 'Good'
  if (score >= 40) return 'Needs Work'
  return 'Poor'
}

/**
 * Colour for a score band.
 *
 * These are status colours on an ordered severity scale, not categorical
 * series colours — so they are always rendered next to the band label and
 * never carry the meaning on their own. Each step is picked for its own
 * surface (light and dark are separate selections, not a flip) and clears
 * 3:1 contrast against it.
 */
export function bandColor(score: number | null | undefined): string {
  const band = scoreBand(score)
  return {
    Poor: 'var(--band-poor)',
    'Needs Work': 'var(--band-fair)',
    Good: 'var(--band-good)',
    Excellent: 'var(--band-excellent)',
  }[band]
}

export function bandTextClass(score: number | null | undefined): string {
  const band = scoreBand(score)
  return {
    Poor: 'text-band-poor',
    'Needs Work': 'text-band-fair',
    Good: 'text-band-good',
    Excellent: 'text-band-excellent',
  }[band]
}

export function bandBadgeVariant(
  score: number | null | undefined,
): 'destructive' | 'warning' | 'default' | 'success' {
  const band = scoreBand(score)
  return { Poor: 'destructive', 'Needs Work': 'warning', Good: 'default', Excellent: 'success' }[
    band
  ] as 'destructive' | 'warning' | 'default' | 'success'
}

export const STATUS_LABEL: Record<AuditStatus, string> = {
  pending: 'Queued',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
}

export const STATUS_VARIANT: Record<AuditStatus, 'muted' | 'default' | 'success' | 'destructive'> = {
  pending: 'muted',
  running: 'default',
  completed: 'success',
  failed: 'destructive',
}

export const EFFORT_LABEL: Record<Effort, string> = {
  quick_win: 'Quick win',
  medium: 'Medium effort',
  strategic: 'Strategic',
}

export const EFFORT_ORDER: Effort[] = ['quick_win', 'medium', 'strategic']

export const IMPACT_VARIANT: Record<Impact, 'destructive' | 'warning' | 'muted'> = {
  high: 'destructive',
  medium: 'warning',
  low: 'muted',
}

export const PROVIDER_LABEL: Record<string, string> = {
  openai: 'OpenAI (ChatGPT)',
  anthropic: 'Anthropic (Claude)',
  perplexity: 'Perplexity',
}
