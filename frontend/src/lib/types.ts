/** Shared API types. Mirrors the backend Pydantic schemas. */

export type UserRole = 'user' | 'admin'
export type AuditStatus = 'pending' | 'running' | 'completed' | 'failed'
export type ProviderName = 'openai' | 'anthropic' | 'perplexity' | 'groq'
export type Effort = 'quick_win' | 'medium' | 'strategic'
export type Impact = 'high' | 'medium' | 'low'

export interface User {
  id: string
  email: string
  full_name: string | null
  role: UserRole
  is_active: boolean
  is_email_verified: boolean
  mfa_enabled: boolean
  notify_audit_complete: boolean
  created_at: string
  last_login_at: string | null
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface LLMApiKey {
  id: string
  provider: ProviderName
  label: string
  key_preview: string
  model: string | null
  is_active: boolean
  /** Ask the provider to answer with live web retrieval where it supports it. */
  use_web_search: boolean
  last_validated_at: string | null
  last_used_at: string | null
  created_at: string
}

export interface ProviderInfo {
  name: ProviderName
  display_name: string
  default_model: string
  /** Suggestions only — any model the key can reach is accepted. */
  models: string[]
  key_format_hint: string
  docs_url: string
  supports_web_search: boolean
  /** True when retrieval cannot be turned off (Perplexity). */
  always_grounded: boolean
}

export interface Business {
  id: string
  name: string
  industry: string | null
  description: string | null
  target_audience: string | null
  location: string | null
  competitors: string[]
  unique_selling_points: string | null
  website_url: string
  key_pages: string[]
  cms_platform: string | null
  created_at: string
  updated_at: string
}

/** One pillar's result inside `pillar_scores`. */
export interface PillarResult {
  key: string
  name: string
  score: number
  weight: number
  effective_weight: number
  skipped: boolean
  skip_reason: string | null
  summary: string
  checks: PillarCheck[]
}

export interface PillarCheck {
  label: string
  passed: boolean | null
  detail: string
  points: number
  max_points: number
}

export interface Recommendation {
  id: string
  title: string
  detail: string
  pillar: string
  effort: Effort
  impact: Impact
  actionable: boolean
}

export interface SovPromptResult {
  prompt: string
  provider: ProviderName
  model: string
  mentioned: boolean
  cited: boolean
  position: number | null
  sentiment: 'positive' | 'neutral' | 'negative' | null
  competitors_mentioned: string[]
  citations: string[]
  excerpt: string
  error: string | null
}

export interface ShareOfVoiceResults {
  tested: boolean
  skip_reason: string | null
  prompts_tested: number
  providers_tested: string[]
  total_calls: number
  failed_calls: number
  mention_rate: number
  citation_rate: number
  average_position: number | null
  sentiment_breakdown: Record<string, number>
  competitor_share: Record<string, number>
  results: SovPromptResult[]
}

export interface AuditSummary {
  id: string
  business_id: string
  business_name: string
  website_url: string
  status: AuditStatus
  geo_score: number | null
  score_band: string | null
  progress: number
  created_at: string
  started_at: string | null
  completed_at: string | null
  has_report: boolean
}

export interface AuditDetail extends AuditSummary {
  questionnaire_answers: Record<string, unknown>
  pillar_scores: Record<string, PillarResult> | null
  share_of_voice_results: ShareOfVoiceResults | null
  recommendations: Recommendation[] | null
  raw_findings: Record<string, unknown> | null
  error_message: string | null
  events: AuditEvent[]
}

export interface AuditEvent {
  id: string
  stage: string
  level: string
  message: string
  created_at: string
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface DashboardStats {
  total_audits: number
  completed_audits: number
  running_audits: number
  average_score: number | null
  latest_score: number | null
  score_delta: number | null
  best_score: number | null
  connected_providers: ProviderName[]
  score_trend: Array<{ date: string; score: number; business: string }>
  pillar_averages: Record<string, number>
  recent_audits: AuditSummary[]
}

export interface AdminStats {
  total_users: number
  active_users_30d: number
  new_users_7d: number
  total_audits: number
  audits_today: number
  audits_7d: number
  running_audits: number
  failed_audits_7d: number
  average_geo_score: number | null
  provider_usage: Record<string, number>
  signups_trend: Array<{ date: string; count: number }>
  audits_trend: Array<{ date: string; count: number }>
}

export interface AdminUserRow extends User {
  audit_count: number
  business_count: number
  api_key_providers: ProviderName[]
  last_audit_at: string | null
}

export interface AdminLogEntry {
  id: string
  action: string
  admin_email: string | null
  target_user_id: string | null
  target_user_email: string | null
  target_type: string | null
  target_id: string | null
  reason: string | null
  metadata: Record<string, unknown>
  created_at: string
}
