import type { AgentContext, AnalysisDetail, AWSAccount, CloudProvider, HistoryItem } from './types'

const BASE = '/api'

// Cache static lists per provider for the session lifetime
const _cachedServices: Partial<Record<CloudProvider, { id: string; name: string; description: string }[]>> = {}
const _cachedRegions: Partial<Record<CloudProvider, string[]>> = {}

async function req<T>(path: string, opts: RequestInit & { skipRedirectOn401?: boolean } = {}): Promise<T> {
  const { skipRedirectOn401, ...fetchOpts } = opts
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      ...fetchOpts,
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(fetchOpts.headers ?? {}) },
    })
  } catch {
    throw new Error('Cannot reach the server. Make sure the backend is running and try again.')
  }
  if (res.status === 401 || res.status === 403) {
    if (!skipRedirectOn401) window.location.href = '/login'
    throw new Error('Session expired — please log in again.')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = body.detail
    const msg = typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.map((d: { msg: string }) => d.msg).join('; ')
        : 'Request failed'
    throw new Error(msg)
  }
  return res.json()
}

export const auth = {
  signup: (email: string, password: string) =>
    req<{ user: { id: number; email: string } }>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  login: (email: string, password: string) =>
    req<{ user: { id: number; email: string } }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  logout: () =>
    req<{ status: string }>('/auth/logout', { method: 'POST' }),

  me: () =>
    req<{ id: number; email: string }>('/auth/me', { skipRedirectOn401: true }),

  changePassword: (current_password: string, new_password: string) =>
    req<{ message: string }>('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password, new_password }),
    }),
}

export const cloud = {
  regions: async (provider: CloudProvider = 'aws') => {
    if (_cachedRegions[provider]) return { regions: _cachedRegions[provider]! }
    const r = await req<{ regions: string[] }>(`/regions?provider=${provider}`)
    _cachedRegions[provider] = r.regions
    return r
  },
  services: async (provider: CloudProvider = 'aws') => {
    if (_cachedServices[provider]) return { services: _cachedServices[provider]! }
    const r = await req<{ services: { id: string; name: string; description: string }[] }>(
      `/services?provider=${provider}`
    )
    _cachedServices[provider] = r.services
    return r
  },
}

export const aws = {
  regions: () => cloud.regions('aws'),
  services: () => cloud.services('aws'),
  accounts: () => req<{ accounts: AWSAccount[] }>('/config/accounts'),
  addAccount: (data: { account_id: string; name: string; email?: string }) =>
    req<{ account: AWSAccount }>('/config/accounts', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  removeAccount: (account_id: string) =>
    req<{ status: string }>(`/config/accounts/${account_id}`, { method: 'DELETE' }),
}

export interface SSOCredential {
  account_id: string
  account_name: string
  role_name: string
  access_key: string
  secret_key: string
  session_token: string
}

// SSO credentials are stored encrypted in sessionStorage to mitigate XSS exposure.
// The encryption key is ephemeral (per-tab-session) and never persisted to disk.
// This is a defence-in-depth measure — credentials are still accessible to the
// same-origin JS context but are not stored in plaintext.

const SSO_CREDS_KEY = 'cost_detective_sso_creds'
const SSO_CREDS_KEY_ENCRYPTED = 'cost_detective_sso_enc'

function _ssoEncryptionKey(): Promise<CryptoKey> {
  const raw = sessionStorage.getItem(SSO_CREDS_KEY_ENCRYPTED)
  if (raw) {
    return crypto.subtle.importKey('raw', Uint8Array.from(atob(raw), c => c.charCodeAt(0)), 'AES-GCM', false, ['encrypt', 'decrypt'])
  }
  const key = crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt'])
  key.then(k => {
    crypto.subtle.exportKey('raw', k).then(rawKey => {
      sessionStorage.setItem(SSO_CREDS_KEY_ENCRYPTED, btoa(String.fromCharCode(...new Uint8Array(rawKey))))
    })
  })
  return key
}

async function _encrypt(creds: SSOCredential[]): Promise<string> {
  const key = await _ssoEncryptionKey()
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const encoded = new TextEncoder().encode(JSON.stringify(creds))
  const encrypted = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, encoded)
  const combined = new Uint8Array(iv.length + encrypted.byteLength)
  combined.set(iv)
  combined.set(new Uint8Array(encrypted), iv.length)
  return btoa(String.fromCharCode(...combined))
}

async function _decrypt(raw: string): Promise<SSOCredential[] | null> {
  try {
    const key = await _ssoEncryptionKey()
    const combined = Uint8Array.from(atob(raw), c => c.charCodeAt(0))
    const iv = combined.slice(0, 12)
    const data = combined.slice(12)
    const decrypted = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, data)
    return JSON.parse(new TextDecoder().decode(decrypted)) as SSOCredential[]
  } catch { return null }
}

export async function saveSSOCreds(creds: SSOCredential[]): Promise<void> {
  try {
    const encrypted = await _encrypt(creds)
    sessionStorage.setItem(SSO_CREDS_KEY, encrypted)
  } catch { /* ignore */ }
}

export async function loadSSOCreds(): Promise<SSOCredential[] | null> {
  try {
    const raw = sessionStorage.getItem(SSO_CREDS_KEY)
    if (!raw) return null
    return await _decrypt(raw)
  } catch { return null }
}

export function clearSSOCreds(): void {
  try {
    sessionStorage.removeItem(SSO_CREDS_KEY)
    sessionStorage.removeItem(SSO_CREDS_KEY_ENCRYPTED)
  } catch { /* ignore */ }
}

type ScanPayload = {
  cloud_provider: CloudProvider
  regions: string[]
  services: string[]
  accounts?: string[]
  use_organizations?: boolean
  subscription_id?: string
  azure_tenant_id?: string
  azure_client_id?: string
  azure_client_secret?: string
  project_id?: string
  aws_access_key_id?: string
  aws_secret_access_key?: string
  gcp_api_key?: string
  ai_provider?: string
  ai_api_key?: string
  sso_credentials?: SSOCredential[]
}

export const sso = {
  start: (start_url: string, region: string) =>
    req<{
      session_id: string
      user_code: string
      verification_uri: string
      verification_uri_complete: string
      expires_in: number
      interval: number
    }>('/sso/start', { method: 'POST', body: JSON.stringify({ start_url, region }) }),

  poll: (session_id: string) =>
    req<{ status: 'pending' | 'authorized' | 'expired' | 'error'; message?: string }>(
      `/sso/poll/${session_id}`
    ),

  accounts: (session_id: string) =>
    req<{
      accounts: Array<{ account_id: string; account_name: string; email: string; roles: string[] }>
    }>(`/sso/accounts/${session_id}`),

  credentials: (session_id: string, selections: Array<{ account_id: string; account_name: string; role_name: string }>) =>
    req<{ credentials: SSOCredential[]; errors: string[] }>('/sso/credentials', {
      method: 'POST',
      body: JSON.stringify({ session_id, selections }),
    }),
}

export const analysis = {
  validate: (payload: Pick<ScanPayload,
    'cloud_provider' | 'subscription_id' | 'azure_tenant_id' | 'azure_client_id' | 'azure_client_secret' |
    'project_id' | 'use_organizations' | 'accounts' |
    'aws_access_key_id' | 'aws_secret_access_key' | 'gcp_api_key' | 'ai_provider' | 'ai_api_key' |
    'sso_credentials'>) =>
    req<{ ok: boolean; message: string }>('/validate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  start: (payload: ScanPayload) =>
    req<{ analysis_id: string; status: string }>('/analyze', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  history: (limit = 100, offset = 0) =>
    req<{ analyses: HistoryItem[] }>(`/history?limit=${limit}&offset=${offset}`),

  get: (id: string) => req<AnalysisDetail>(`/history/${id}`),

  delete: (id: string) => req<{ status: string }>(`/history/${id}`, { method: 'DELETE' }),
}

export interface CostEstimateSuggestion {
  type: string
  title: string
  description: string
  potential_savings: number
  action: string
}

export interface ResourceEstimate {
  resource_name: string
  resource_type: string
  instance_type?: string
  volume_type?: string
  size_gb?: number
  monthly_cost: number
  hourly_cost: number
  details: string
  breakdown?: Record<string, number>
  suggestions?: CostEstimateSuggestion[]
  estimate_note?: string
}

export interface FreeTierLimit {
  name: string
  type: 'always-free' | '12-month'
  limits: Record<string, number | string>
  description: string
  annual_limit: string
}

export interface FreeTierAnalysis {
  within_limits: boolean
  usage_summary: Record<string, number>
  details: string[]
  note: string
}

export interface CostEstimateReport {
  id: string
  total_monthly_cost: number
  total_yearly_cost: number
  resource_count: number
  free_resource_count: number
  unknown_resource_count: number
  service_breakdown: Record<string, number>
  top_services_by_cost: Array<{ service: string; monthly_cost: number; percentage: number }>
  resource_estimates: ResourceEstimate[]
  unknown_resources: Array<{ resource_name: string; resource_type: string; reason: string }>
  suggestions: CostEstimateSuggestion[]
  total_potential_savings: number
  provider_breakdown?: Record<string, number>
  free_tier_eligible?: Array<ResourceEstimate>
  free_tier_limits?: Record<string, FreeTierLimit>
  free_tier_analysis?: FreeTierAnalysis
}

export interface EstimateResponse {
  format: string
  provider: string
  resources_found: number
  report: CostEstimateReport
}

export interface GitEstimateResponse {
  repo_url: string
  provider: string
  resources_found: number
  templates_found: number
  report: CostEstimateReport
}

async function reqFormData<T>(path: string, formData: FormData): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      credentials: 'include',
      body: formData,
    })
  } catch {
    throw new Error('Cannot reach the server. Make sure the backend is running and try again.')
  }
  if (res.status === 401 || res.status === 403) {
    window.location.href = '/login'
    throw new Error('Session expired — please log in again.')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = body.detail
    const msg = typeof detail === 'string' ? detail : 'Request failed'
    throw new Error(msg)
  }
  return res.json()
}

export const estimate = {
  paste: (content: string, format = 'auto', provider?: string) =>
    req<EstimateResponse>('/estimate', {
      method: 'POST',
      body: JSON.stringify({ content, format, provider }),
    }),

  git: (repo_url: string, branch?: string, provider?: string) =>
    req<GitEstimateResponse>('/estimate/git', {
      method: 'POST',
      body: JSON.stringify({ repo_url, branch, provider }),
    }),

  upload: (files: File[]) => {
    const formData = new FormData()
    for (const file of files) {
      formData.append('files', file)
    }
    return reqFormData<EstimateResponse>('/estimate/upload', formData)
  },

  formats: () =>
    req<{ formats: Array<{ id: string; name: string; extensions: string[]; description: string }>; estimation_note: string }>(
      '/estimate/formats'
    ),
}

// ─── Cost Explorer ───────────────────────────────────────────────────────────

export interface CostExplorerDay {
  date: string
  total: number
  services: Record<string, number>
}

export interface CostExplorerService {
  name: string
  total: number
  percentage: number
}

export interface CostExplorerResponse {
  available: boolean
  reason?: string
  period?: { start: string; end: string; days: number }
  total_spend?: number
  average_daily_cost?: number
  projected_monthly_cost?: number
  projected_annual_cost?: number
  daily_costs?: CostExplorerDay[]
  top_services?: CostExplorerService[]
}

export interface CostForecastEntry {
  period: { Start: string; End: string }
  mean: number
}

export interface CostForecastResponse {
  available: boolean
  reason?: string
  forecasts?: CostForecastEntry[]
}

export interface RightsizingRecommendation {
  resource_id: string
  account_id: string
  rightsizing_type: string
  current_instance_type: string
  current_hours: number
  recommended_instance_type: string
  estimated_monthly_savings: number
  estimated_monthly_cost_after: number
}

export interface CostVariationPeriod {
  period_days: number
  total_cost: number
  top_services: Array<{ name: string; total: number; percentage: number }>
}

export interface AwarenessItem {
  id: string
  date: string
  category: string
  title: string
  summary: string
  impact: string
  link: string
  action: string
}

export interface AwarenessResponse {
  available: boolean
  last_updated: string
  total_items: number
  items: AwarenessItem[]
  note: string
}

export interface CostVariationChange {
  current_total: number
  previous_total: number
  change_percentage: number
}

export interface CostVariationResponse {
  available: boolean
  reason?: string
  periods?: Record<string, CostVariationPeriod>
  changes?: Record<string, CostVariationChange>
}

function _credBody(accessKey?: string, secretKey?: string, sessionToken?: string): Record<string, string | undefined> {
  return {
    aws_access_key_id: accessKey || undefined,
    aws_secret_access_key: secretKey || undefined,
    aws_session_token: sessionToken || undefined,
  }
}

export const cost = {
  explorer: (accessKey = '', secretKey = '', sessionToken = '', days = 30) =>
    req<CostExplorerResponse>('/cost/explorer', {
      method: 'POST',
      body: JSON.stringify({
        ..._credBody(accessKey, secretKey, sessionToken),
        days,
      }),
    }),

  forecast: (accessKey = '', secretKey = '', sessionToken = '') =>
    req<CostForecastResponse>('/cost/forecast', {
      method: 'POST',
      body: JSON.stringify(_credBody(accessKey, secretKey, sessionToken)),
    }),

  variation: (accessKey = '', secretKey = '', sessionToken = '') =>
    req<CostVariationResponse>('/cost/variation', {
      method: 'POST',
      body: JSON.stringify(_credBody(accessKey, secretKey, sessionToken)),
    }),

  awareness: (category?: string, limit = 10) =>
    req<AwarenessResponse>(`/cost/awareness?limit=${limit}${category ? `&category=${encodeURIComponent(category)}` : ''}`),

  rightsizing: (accessKey = '', secretKey = '', sessionToken = '') =>
    req<{ recommendations: RightsizingRecommendation[] }>('/cost/rightsizing', {
      method: 'POST',
      body: JSON.stringify(_credBody(accessKey, secretKey, sessionToken)),
    }),

  explain: (serviceTotals: Record<string, number>, totalSpend: number, changes: Record<string, unknown> = {}) =>
    req<{ explanation: string }>('/cost/explain', {
      method: 'POST',
      body: JSON.stringify({ service_totals: serviceTotals, total_spend: totalSpend, changes }),
    }),

  forecastNarrative: (forecasts: CostForecastEntry[], currentTotal: number) =>
    req<{ narrative: string }>('/cost/forecast/narrative', {
      method: 'POST',
      body: JSON.stringify({ forecasts, current_total: currentTotal }),
    }),

  rightsizingExplain: (recommendation: RightsizingRecommendation) =>
    req<{ explanation: string }>('/cost/rightsizing/explain', {
      method: 'POST',
      body: JSON.stringify({ recommendation }),
    }),

  personalizedAwareness: (activeServices: string[] = []) =>
    req<{ tips: Array<{ category: string; title: string; summary: string; impact: string; action: string }> }>(
      '/cost/awareness/personalized', {
        method: 'POST',
        body: JSON.stringify({ active_services: activeServices }),
      }),
}

// ─── Teams / RBAC ────────────────────────────────────────────────────────────

export const teams = {
  list: () => req<import('./types').Organization[]>('/teams'),
  get: (orgId: number) => req<import('./types').Organization>(`/teams/${orgId}`),
  create: (name: string) =>
    req<import('./types').Organization>('/teams', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  update: (orgId: number, name: string) =>
    req<import('./types').Organization>(`/teams/${orgId}`, {
      method: 'PUT',
      body: JSON.stringify({ name }),
    }),
  delete: (orgId: number) =>
    req<{ message: string }>(`/teams/${orgId}`, { method: 'DELETE' }),

  members: {
    list: (orgId: number) =>
      req<import('./types').Member[]>(`/teams/${orgId}/members`),
    add: (orgId: number, userId: number, role: string) =>
      req<import('./types').Member>(`/teams/${orgId}/members`, {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, role }),
      }),
    updateRole: (orgId: number, userId: number, role: string) =>
      req<{ message: string }>(`/teams/${orgId}/members/${userId}/role`, {
        method: 'PUT',
        body: JSON.stringify({ role }),
      }),
    remove: (orgId: number, userId: number) =>
      req<{ message: string }>(`/teams/${orgId}/members/${userId}`, {
        method: 'DELETE',
      }),
  },

  invitations: {
    list: (orgId: number) =>
      req<import('./types').Invitation[]>(`/teams/${orgId}/invitations`),
    create: (orgId: number, email: string, role = 'member') =>
      req<import('./types').Invitation>(`/teams/${orgId}/invitations`, {
        method: 'POST',
        body: JSON.stringify({ email, role }),
      }),
    accept: (token: string) =>
      req<{ message: string }>(`/teams/invitations/${token}/accept`, {
        method: 'POST',
      }),
  },
}

// ─── Alerts ──────────────────────────────────────────────────────────────────

export const alerts = {
  getConfig: () => req<import('./types').AlertConfig>('/alerts/config'),
  updateConfig: (config: { email?: string | null; slack_webhook?: string | null; notify_on: string[] }) =>
    req<import('./types').AlertConfig>('/alerts/config', {
      method: 'PUT',
      body: JSON.stringify(config),
    }),
  test: () => req<{ status: string }>('/alerts/test', { method: 'POST' }),
  history: (limit = 50) =>
    req<{ history: import('./types').AlertHistoryItem[] }>(`/alerts/history?limit=${limit}`),
}

// ─── RI / Savings Plans ──────────────────────────────────────────────────────

export const rightsizing = {
  riRecommendations: (accessKey = '', secretKey = '', sessionToken = '') =>
    req<{ recommendations: import('./types').RIRecommendation[]; error?: string }>('/cost/ri-recommendations', {
      method: 'POST',
      body: JSON.stringify(_credBody(accessKey, secretKey, sessionToken)),
    }),

  savingsPlans: (accessKey = '', secretKey = '', sessionToken = '') =>
    req<{ recommendations: import('./types').SavingsPlanRecommendation[]; error?: string }>('/cost/savings-plans', {
      method: 'POST',
      body: JSON.stringify(_credBody(accessKey, secretKey, sessionToken)),
    }),
}

export const freeTier = {
  get: (provider: string = 'all') =>
    req<Record<string, unknown>>(`/free-tier?provider=${provider}`),

  summary: (provider: string = 'all') =>
    req<{ services: unknown[] }>(`/free-tier/summary?provider=${provider}`),

  check: (provider: string, resources: unknown[] = []) =>
    req<{ eligible: boolean; message: string }>(`/free-tier/check?provider=${provider}&resources=${encodeURIComponent(JSON.stringify(resources))}`),

  recommendations: (usageData: Record<string, unknown>, provider = 'aws') =>
    req<{ recommendations: Array<{ title: string; description: string; action: string; impact: string }> }>(
      '/free-tier/recommendations', {
        method: 'POST',
        body: JSON.stringify({ usage_data: usageData, provider }),
      }),

  checkAI: (resourceTypes: string[], provider = 'aws') =>
    req<{ eligible: boolean; services_checked: number; details: Array<{ resource_type: string; eligible: boolean; limit: string; condition: string; explanation: string }> }>(
      '/free-tier/check/ai', {
        method: 'POST',
        body: JSON.stringify({ resource_types: resourceTypes, provider }),
      }),
}

export const estimateAI = {
  insights: (resourcesFound: number, totalCost: number, serviceBreakdown: Record<string, number>) =>
    req<{ insights: string }>('/estimate/insights', {
      method: 'POST',
      body: JSON.stringify({ resources_found: resourcesFound, total_cost: totalCost, service_breakdown: serviceBreakdown }),
    }),
}

export const freeTierUsage = {
  get: (provider: string) =>
    req<unknown>(`/free-tier/usage/${provider}`),
}

export const infraViz = {
  parse: (content: string, fileType: string = 'terraform') =>
    req<unknown>('/infra/parse', {
      method: 'POST',
      body: JSON.stringify({ content, file_type: fileType }),
    }),

  validate: (content: string, fileType: string = 'terraform') =>
    req<unknown>('/infra/validate', {
      method: 'POST',
      body: JSON.stringify({ content, file_type: fileType }),
    }),

  scanProject: (directory: string, maxDepth: number = 5) =>
    req<unknown>('/infra/scan-project', {
      method: 'POST',
      body: JSON.stringify({ directory, max_depth: maxDepth }),
    }),

  scanGit: (repoUrl: string) =>
    req<unknown>(`/infra/scan-git?repo_url=${encodeURIComponent(repoUrl)}`),

  summarize: (nodes: unknown[], edges: unknown[]) =>
    req<{ summary: string }>('/infra/summarize', {
      method: 'POST',
      body: JSON.stringify({ nodes, edges }),
    }),

  preApply: (content: string, fileType: string = 'terraform') =>
    req<{ nodes: unknown[]; edges: unknown[]; suggestions: unknown[]; summary: Record<string, unknown>; architecture_summary: string; resource_count_by_type: Record<string, number> }>(
      '/infra/pre-apply', {
        method: 'POST',
        body: JSON.stringify({ content, file_type: fileType }),
      }),

  validateAI: (rawResources: Record<string, unknown>) =>
    req<{ issues: Array<{ severity: string; category: string; resource_id: string; message: string; explanation: string; fix: string }> }>(
      '/infra/validate/ai', {
        method: 'POST',
        body: JSON.stringify({ raw_resources: rawResources }),
      }),
  fromScan: () =>
    req<{ nodes: unknown[]; edges: unknown[]; broken_connections: unknown[]; suggestions: unknown[]; summary: Record<string, unknown> }>(
      '/infra/from-scan', { method: 'POST' }),
}

export interface AgentAnalysisRequest {
  action: 'analyze' | 'validate' | 'explain'
  content: string
  file_type: 'terraform' | 'cloudformation' | 'kubernetes' | 'docker-compose'
  options?: {
    focus?: 'cost' | 'security' | 'performance' | 'all'
    provider?: 'aws' | 'azure' | 'gcp'
  }
}

export const agent = {
  analyze: (payload: AgentAnalysisRequest) =>
    req<unknown>('/agent/analyze', { method: 'POST', body: JSON.stringify(payload) }),
  validate: (payload: AgentAnalysisRequest) =>
    req<unknown>('/agent/validate', { method: 'POST', body: JSON.stringify(payload) }),
  explain: (payload: AgentAnalysisRequest) =>
    req<unknown>('/agent/explain', { method: 'POST', body: JSON.stringify(payload) }),
  complete: (payload: { prompt: string; system?: string; max_tokens?: number; temperature?: number }) =>
    req<{ success: boolean; response: string }>('/agent/complete', { method: 'POST', body: JSON.stringify(payload) }),
  health: () =>
    req<{ status: string; environment: string; model: string; services: { ai: boolean; database: boolean; cache: boolean } }>('/agent/health'),

  // Chat
  chat: (payload: {
    messages: Array<{ role: string; content: string }>
    context?: AgentContext
    conversation_id?: number
    max_tokens?: number
    temperature?: number
    provider?: string
  }) => req<{ response: string; conversation_id?: number }>('/agent/chat', { method: 'POST', body: JSON.stringify(payload) }),

  // Conversations
  conversations: {
    list: () => req<{ conversations: Array<{ id: number; title: string; created_at: string; updated_at: string }> }>('/agent/conversations'),
    create: (title?: string) => req<{ id: number; title: string }>('/agent/conversations', { method: 'POST', body: JSON.stringify({ title }) }),
    messages: (id: number) => req<{ messages: Array<{ id: number; role: string; content: string; model_used?: string; created_at: string }> }>(`/agent/conversations/${id}`),
    delete: (id: number) => req<{ success: boolean }>(`/agent/conversations/${id}`, { method: 'DELETE' }),
  },

  // Advanced capabilities
  generateFix: (issue: Record<string, unknown>, context?: Record<string, unknown>) =>
    req<{ command: string; explanation: string; prerequisites: string[]; rollback: string; impact: string }>(
      '/agent/fix', { method: 'POST', body: JSON.stringify({ issue, context }) }),

  simulateCost: (resource: Record<string, unknown>, proposedChange: string) =>
    req<{ current_monthly_cost: number; new_monthly_cost: number; monthly_savings: number; annual_savings: number; risks: string[]; recommendation: string; explanation: string }>(
      '/agent/simulate', { method: 'POST', body: JSON.stringify({ resource, proposed_change: proposedChange }) }),

  complianceCheck: (resources: Record<string, unknown>, framework = 'cis') =>
    req<{ framework: string; score: number; passed_checks: number; total_checks: number; violations: Array<{ control: string; severity: string; resource: string; description: string; fix: string }>; recommendations: string[] }>(
      '/agent/compliance', { method: 'POST', body: JSON.stringify({ resources, framework }) }),

  detectAnomalies: (currentScan: Record<string, unknown>, historicalScans: Record<string, unknown>[]) =>
    req<{ anomalies: Array<{ type: string; severity: string; message: string; details: string; recommendation: string }> }>(
      '/agent/anomalies', { method: 'POST', body: JSON.stringify({ current_scan: currentScan, historical_scans: historicalScans }) }),

  generateIaC: (description: string, format = 'terraform', provider = 'aws') =>
    req<{ code: string; format: string; explanation: string; estimated_monthly_cost: number; warnings: string[] }>(
      '/agent/generate-iac', { method: 'POST', body: JSON.stringify({ description, format, provider }) }),

  resourceLookup: (query: string) =>
    req<{ response: string }>(
      '/agent/resource-lookup', { method: 'POST', body: JSON.stringify({ query }) }),
}
