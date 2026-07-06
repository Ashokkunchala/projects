export interface Issue {
  service: string
  resource_name: string
  resource_id: string
  region: string
  account_id?: string
  account_name?: string
  issue_type: 'over-provisioned' | 'unused' | 'misconfigured' | 'non-optimized'
  severity: 'high' | 'medium' | 'low'
  explanation: string
  fix_command: string
  potential_monthly_savings: number
}

export interface AnalysisResult {
  summary: string
  total_resources: number
  issues_found: number
  estimated_monthly_savings: number
  estimated_annual_savings: number
  issues: Issue[]
}

export interface ProgressMessage {
  message: string
  status: 'in_progress' | 'complete' | 'error' | 'keepalive'
  data?: AnalysisResult
}

export type CloudProvider = 'aws' | 'azure' | 'gcp'

export interface HistoryItem {
  id: string
  cloud_provider?: CloudProvider
  regions: string[]
  services: string[]
  accounts?: string[]
  resources_scanned: number
  issues_found: number
  estimated_savings: string | null
  status: 'running' | 'complete' | 'failed'
  error_message?: string | null
  ai_summary?: string | null
  created_at: string
}

export interface User {
  id: number
  email: string
}

export interface AWSAccount {
  account_id: string
  name: string
  email?: string
  role_arn?: string
  profile_name?: string
}

export interface AnalysisDetail extends HistoryItem {
  analysis_result: AnalysisResult | null
  ai_summary?: string | null
}

// ─── Chat / Agent Types ─────────────────────────────────────────────────────

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface AgentContext {
  analysis_id?: string
  analysis_result?: Record<string, unknown>
  scan_data?: Record<string, unknown>
  page?: string
  user_services?: string[]
}

export interface Conversation {
  id: number
  title: string
  created_at: string
  updated_at: string
}

export interface ConversationMessage {
  id: number
  role: string
  content: string
  model_used?: string
  metadata?: string
  created_at: string
}

// ─── Teams / RBAC Types ───────────────────────────────────────────────────────

export interface Organization {
  id: number
  name: string
  owner_id: number
  created_at: string
  updated_at: string
}

export interface Member {
  id: number
  organization_id: number
  user_id: number
  role: 'owner' | 'admin' | 'member' | 'viewer'
  invited_by: number
  created_at: string
  email: string
}

export interface Invitation {
  id: number
  organization_id: number
  email: string
  role: string
  token: string
  invited_by: number
  expires_at: string
  accepted: boolean
  created_at: string
}

// ─── Alert Types ─────────────────────────────────────────────────────────────

export interface AlertConfig {
  email: string | null
  slack_webhook: string | null
  notify_on: string[]
}

export interface AlertHistoryItem {
  id: number
  alert_type: string
  title: string
  message: string | null
  severity: string
  channel: string | null
  sent_at: string
}

// ─── RI / Savings Plan Types ─────────────────────────────────────────────────

export interface RIRecommendation {
  service: string
  account_id: string
  current_instance_type: string
  recommended_plan: string
  upfront: string
  term: string
  estimated_annual_savings: number
  estimated_monthly_savings: number
  coverage: number
  explanation: string
}

export interface SavingsPlanRecommendation {
  service: string
  account_id: string
  current_instance_type: string
  recommended_plan: string
  upfront: string
  term: string
  estimated_annual_savings: number
  estimated_monthly_savings: number
  coverage: number
  explanation: string
}
