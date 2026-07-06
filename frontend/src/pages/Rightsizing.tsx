import { useState } from 'react'
import {
  Lightbulb, RefreshCw, AlertTriangle, Key, Eye, EyeOff,
  DollarSign, Calendar, Shield,
} from 'lucide-react'
import { rightsizing as rightsizingApi } from '../api'
import type { RIRecommendation, SavingsPlanRecommendation } from '../types'

const TERM_LABELS: Record<string, string> = {
  '1year': '1 Year',
  '3year': '3 Years',
}

const UPFRONT_LABELS: Record<string, string> = {
  no: 'No Upfront',
  partial: 'Partial Upfront',
  all: 'All Upfront',
}

function fmtCurrency(n: number) {
  return `$${(n || 0).toFixed(2)}`
}

function RICard({ rec }: { rec: RIRecommendation }) {
  return (
    <div className="card" style={{ padding: '14px 18px' }}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Shield size={14} style={{ color: '#f59e0b' }} />
            <span className="font-semibold text-sm text-white truncate">{rec.service}</span>
            {rec.account_id && (
              <span className="text-xs font-mono" style={{ color: 'var(--color-text-tertiary)' }}>
                {rec.account_id}
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            {rec.current_instance_type && (
              <span>{rec.current_instance_type}</span>
            )}
            {rec.recommended_plan && (
              <span>→ <span style={{ color: '#10b981' }}>{rec.recommended_plan}</span></span>
            )}
            <span>
              {TERM_LABELS[rec.term] || rec.term} · {UPFRONT_LABELS[rec.upfront] || rec.upfront}
            </span>
            {rec.coverage > 0 && (
              <span>{rec.coverage.toFixed(1)}% coverage</span>
            )}
          </div>
          {rec.explanation && (
            <p className="text-xs mt-1.5 leading-relaxed" style={{ color: 'var(--color-text-tertiary)' }}>
              {rec.explanation}
            </p>
          )}
        </div>
        <div className="text-right shrink-0">
          {rec.estimated_monthly_savings > 0 && (
            <div>
              <span className="badge-high" style={{ fontSize: '0.7rem' }}>
                -{fmtCurrency(rec.estimated_monthly_savings)}/mo
              </span>
            </div>
          )}
          {rec.estimated_annual_savings > 0 && (
            <div className="mt-1">
              <span className="text-xs font-medium" style={{ color: '#10b981' }}>
                {fmtCurrency(rec.estimated_annual_savings)}/yr
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function SavingsPlanCard({ rec }: { rec: SavingsPlanRecommendation }) {
  return (
    <div className="card" style={{ padding: '14px 18px' }}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <DollarSign size={14} style={{ color: '#10b981' }} />
            <span className="font-semibold text-sm text-white truncate">
              {rec.service} Savings Plan
            </span>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            <span>{rec.recommended_plan}</span>
            <span>{TERM_LABELS[rec.term] || rec.term} · {UPFRONT_LABELS[rec.upfront] || rec.upfront}</span>
            {rec.coverage > 0 && <span>{rec.coverage.toFixed(1)}% coverage</span>}
          </div>
          {rec.explanation && (
            <p className="text-xs mt-1.5 leading-relaxed" style={{ color: 'var(--color-text-tertiary)' }}>
              {rec.explanation}
            </p>
          )}
        </div>
        <div className="text-right shrink-0">
          {rec.estimated_monthly_savings > 0 && (
            <div>
              <span className="badge-high" style={{ fontSize: '0.7rem' }}>
                -{fmtCurrency(rec.estimated_monthly_savings)}/mo
              </span>
            </div>
          )}
          {rec.estimated_annual_savings > 0 && (
            <div className="mt-1">
              <span className="text-xs font-medium" style={{ color: '#10b981' }}>
                {fmtCurrency(rec.estimated_annual_savings)}/yr
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function Rightsizing() {
  const [showCreds, setShowCreds] = useState(false)
  const [showSecret, setShowSecret] = useState(false)
  const [awsAccessKey, setAwsAccessKey] = useState('')
  const [awsSecretKey, setAwsSecretKey] = useState('')
  const [awsSessionToken, setAwsSessionToken] = useState('')

  const [riRecs, setRiRecs] = useState<RIRecommendation[] | null>(null)
  const [spRecs, setSpRecs] = useState<SavingsPlanRecommendation[] | null>(null)
  const [loadingRI, setLoadingRI] = useState(false)
  const [loadingSP, setLoadingSP] = useState(false)
  const [error, setError] = useState('')
  const [riError, setRiError] = useState('')
  const [spError, setSpError] = useState('')

  const _ak = awsAccessKey.trim()
  const _sk = awsSecretKey.trim()
  const _st = awsSessionToken.trim() || undefined

  const fetchRI = async () => {
    if (!_ak || !_sk) { setError('Enter AWS credentials first'); return }
    setLoadingRI(true)
    setError('')
    setRiError('')
    try {
      const data = await rightsizingApi.riRecommendations(_ak, _sk, _st)
      if (data.error) {
        setRiError(data.error)
        setRiRecs(data.recommendations || [])
      } else {
        setRiRecs(data.recommendations || [])
      }
    } catch (e: unknown) {
      setRiError(e instanceof Error ? e.message : 'Failed to fetch RI recommendations')
      setRiRecs([])
    } finally {
      setLoadingRI(false)
    }
  }

  const fetchSP = async () => {
    if (!_ak || !_sk) { setError('Enter AWS credentials first'); return }
    setLoadingSP(true)
    setError('')
    setSpError('')
    try {
      const data = await rightsizingApi.savingsPlans(_ak, _sk, _st)
      if (data.error) {
        setSpError(data.error)
        setSpRecs(data.recommendations || [])
      } else {
        setSpRecs(data.recommendations || [])
      }
    } catch (e: unknown) {
      setSpError(e instanceof Error ? e.message : 'Failed to fetch Savings Plan recommendations')
      setSpRecs([])
    } finally {
      setLoadingSP(false)
    }
  }

  const hasRecs = (riRecs && riRecs.length > 0) || (spRecs && spRecs.length > 0)

  const totalMonthlySavings = (riRecs ? riRecs.reduce((s, r) => s + (r.estimated_monthly_savings || 0), 0) : 0) +
    (spRecs ? spRecs.reduce((s, r) => s + (r.estimated_monthly_savings || 0), 0) : 0)

  const totalAnnualSavings = (riRecs ? riRecs.reduce((s, r) => s + (r.estimated_annual_savings || 0), 0) : 0) +
    (spRecs ? spRecs.reduce((s, r) => s + (r.estimated_annual_savings || 0), 0) : 0)

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">RI & Savings Plans</h1>
        <p className="text-sm mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>
          Reserved Instance and Savings Plan recommendations from AWS Cost Explorer
        </p>
      </div>

      {/* Summary banner */}
      {hasRecs && (
        <div className="card" style={{
          padding: '16px 20px',
          background: 'linear-gradient(135deg, rgba(16,185,129,0.08), rgba(5,150,105,0.04))',
          border: '1px solid rgba(16,185,129,0.2)',
        }}>
          <div className="flex items-center gap-3">
            <DollarSign size={20} style={{ color: '#10b981' }} />
            <div>
              <p className="text-sm font-semibold text-white">
                Potential Savings: {fmtCurrency(totalMonthlySavings)}/month
              </p>
              {totalAnnualSavings > 0 && (
                <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                  {fmtCurrency(totalAnnualSavings)}/year with recommended commitments
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* AWS Credentials */}
      <div className="card" style={{ padding: '12px 16px' }}>
        <button onClick={() => setShowCreds(!showCreds)}
          className="flex items-center gap-2 text-sm font-medium w-full"
          style={{ color: 'var(--color-text-secondary)' }}>
          <Key size={14} />
          AWS Credentials
          <span style={{ marginLeft: 'auto', fontSize: '0.72rem', color: 'var(--color-text-tertiary)' }}>
            {_ak ? 'configured' : 'required for Cost Explorer'}
          </span>
        </button>
        {showCreds && (
          <div className="mt-3 space-y-2">
            <input type="text" placeholder="Access Key ID"
              value={awsAccessKey} onChange={(e) => setAwsAccessKey(e.target.value)}
              className="input text-xs" />
            <div className="relative">
              <input type={showSecret ? 'text' : 'password'} placeholder="Secret Access Key"
                value={awsSecretKey} onChange={(e) => setAwsSecretKey(e.target.value)}
                className="input text-xs w-full pr-8" />
              <button onClick={() => setShowSecret(!showSecret)}
                className="absolute right-2 top-1/2 -translate-y-1/2"
                style={{ color: 'var(--color-text-tertiary)' }}>
                {showSecret ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
            <input type="text" placeholder="Session Token (optional)"
              value={awsSessionToken} onChange={(e) => setAwsSessionToken(e.target.value)}
              className="input text-xs" />
          </div>
        )}
      </div>

      {error && (
        <div className="flex items-start gap-2 p-4 rounded-lg"
          style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
          <AlertTriangle size={16} color="#ef4444" style={{ marginTop: 2, flexShrink: 0 }} />
          <p style={{ color: '#ef4444', fontSize: '0.85rem' }}>{error}</p>
        </div>
      )}

      {/* ── Reserved Instances ── */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-white text-sm flex items-center gap-1.5">
            <Shield size={15} style={{ color: '#f59e0b' }} />
            Reserved Instance Recommendations
          </h2>
          <button onClick={fetchRI} disabled={loadingRI}
            className="btn-primary text-xs flex items-center gap-1 px-3 py-1.5">
            {loadingRI ? <RefreshCw size={12} className="animate-spin" /> : <Lightbulb size={12} />}
            {loadingRI ? 'Loading…' : 'Fetch Recommendations'}
          </button>
        </div>

        {riError && (
          <p className="text-xs flex items-center gap-1" style={{ color: '#f59e0b' }}>
            <AlertTriangle size={11} /> {riError}
          </p>
        )}

        {riRecs === null && !loadingRI && (
          <div className="card text-center py-8" style={{ color: 'var(--color-text-tertiary)' }}>
            <Shield size={24} className="mx-auto mb-2 opacity-40" />
            <p className="text-xs">Click "Fetch Recommendations" to load RI data</p>
          </div>
        )}

        {loadingRI && (
          <div className="space-y-2">
            {[1, 2].map((n) => (
              <div key={n} className="card" style={{ padding: '14px 18px' }}>
                <div className="h-4 rounded w-48" style={{ background: 'var(--color-section-bg)' }} />
                <div className="h-3 rounded w-64 mt-2" style={{ background: 'var(--color-section-bg)' }} />
              </div>
            ))}
          </div>
        )}

        {riRecs !== null && !loadingRI && riRecs.length === 0 && !riError && (
          <div className="card text-center py-8" style={{ color: 'var(--color-text-tertiary)' }}>
            <p className="text-xs font-medium">No RI recommendations available</p>
            <p className="text-xs mt-0.5">This could mean your instances are already optimally covered.</p>
          </div>
        )}

        {riRecs !== null && riRecs.length > 0 && (
          <div className="space-y-1.5">
            {riRecs.map((rec, i) => (
              <RICard key={i} rec={rec} />
            ))}
          </div>
        )}

        {riRecs !== null && !loadingRI && (
          <button onClick={() => setRiRecs(null)} className="btn-ghost text-xs">Clear</button>
        )}
      </div>

      {/* ── Savings Plans ── */}
      <div className="space-y-3 pt-4 border-t" style={{ borderColor: 'var(--color-section-border)' }}>
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-white text-sm flex items-center gap-1.5">
            <DollarSign size={15} style={{ color: '#10b981' }} />
            Savings Plan Recommendations
          </h2>
          <button onClick={fetchSP} disabled={loadingSP}
            className="btn-primary text-xs flex items-center gap-1 px-3 py-1.5">
            {loadingSP ? <RefreshCw size={12} className="animate-spin" /> : <Lightbulb size={12} />}
            {loadingSP ? 'Loading…' : 'Fetch Recommendations'}
          </button>
        </div>

        {spError && (
          <p className="text-xs flex items-center gap-1" style={{ color: '#f59e0b' }}>
            <AlertTriangle size={11} /> {spError}
          </p>
        )}

        {spRecs === null && !loadingSP && (
          <div className="card text-center py-8" style={{ color: 'var(--color-text-tertiary)' }}>
            <DollarSign size={24} className="mx-auto mb-2 opacity-40" />
            <p className="text-xs">Click "Fetch Recommendations" to load Savings Plan data</p>
          </div>
        )}

        {loadingSP && (
          <div className="space-y-2">
            {[1, 2].map((n) => (
              <div key={n} className="card" style={{ padding: '14px 18px' }}>
                <div className="h-4 rounded w-48" style={{ background: 'var(--color-section-bg)' }} />
                <div className="h-3 rounded w-64 mt-2" style={{ background: 'var(--color-section-bg)' }} />
              </div>
            ))}
          </div>
        )}

        {spRecs !== null && !loadingSP && spRecs.length === 0 && !spError && (
          <div className="card text-center py-8" style={{ color: 'var(--color-text-tertiary)' }}>
            <p className="text-xs font-medium">No Savings Plan recommendations available</p>
          </div>
        )}

        {spRecs !== null && spRecs.length > 0 && (
          <div className="space-y-1.5">
            {spRecs.map((rec, i) => (
              <SavingsPlanCard key={i} rec={rec} />
            ))}
          </div>
        )}

        {spRecs !== null && !loadingSP && (
          <button onClick={() => setSpRecs(null)} className="btn-ghost text-xs">Clear</button>
        )}
      </div>
    </div>
  )
}
