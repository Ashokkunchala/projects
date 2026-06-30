import { useState } from 'react'
import {
  BarChart3, TrendingUp, TrendingDown, DollarSign, AlertTriangle,
  RefreshCw, Settings, Download, Lightbulb, Key, Eye, EyeOff,
} from 'lucide-react'
import { cost } from '../api'
import type {
  CostExplorerResponse, CostExplorerDay, CostExplorerService,
  CostForecastResponse, RightsizingRecommendation, CostVariationResponse,
  CostVariationPeriod, CostVariationChange, AwarenessItem,
} from '../api'

type Tab = 'overview' | 'forecast' | 'rightsizing'

export default function CostReports() {
  const [tab, setTab] = useState<Tab>('overview')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [costData, setCostData] = useState<CostExplorerResponse | null>(null)
  const [forecast, setForecast] = useState<CostForecastResponse | null>(null)
  const [variation, setVariation] = useState<CostVariationResponse | null>(null)
  const [rightsizing, setRightsizing] = useState<RightsizingRecommendation[] | null>(null)
  const [awareness, setAwareness] = useState<AwarenessItem[] | null>(null)
  const [awarenessTab, setAwarenessTab] = useState('all')
  const [showCreds, setShowCreds] = useState(false)
  const [showSecret, setShowSecret] = useState(false)
  const [awsAccessKey, setAwsAccessKey] = useState('')
  const [awsSecretKey, setAwsSecretKey] = useState('')
  const [awsSessionToken, setAwsSessionToken] = useState('')

  const _ak = awsAccessKey.trim()
  const _sk = awsSecretKey.trim()
  const _st = awsSessionToken.trim() || undefined

  const fetchCostData = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await cost.explorer(_ak, _sk, _st)
      setCostData(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to fetch cost data')
    } finally {
      setLoading(false)
    }
  }

  const fetchVariation = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await cost.variation(_ak, _sk, _st)
      setVariation(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to fetch cost variation')
    } finally {
      setLoading(false)
    }
  }

  const fetchForecast = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await cost.forecast(_ak, _sk, _st)
      setForecast(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to fetch forecast')
    } finally {
      setLoading(false)
    }
  }

  const fetchRightsizing = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await cost.rightsizing(_ak, _sk, _st)
      setRightsizing(data.recommendations)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to fetch rightsizing recommendations')
    } finally {
      setLoading(false)
    }
  }

  const maxDailyCost = costData?.daily_costs
    ? Math.max(...costData.daily_costs.map(d => d.total), 0.01)
    : 1

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-8">

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Cost Reports</h1>
        <p style={{ color: 'var(--color-text-secondary)', fontSize: '0.88rem', marginTop: 4 }}>
          Analyze current AWS spending, forecast future costs, and get rightsizing recommendations.
        </p>
      </div>

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
              value={awsAccessKey} onChange={e => setAwsAccessKey(e.target.value)}
              className="input text-xs" />
            <div className="relative">
              <input type={showSecret ? 'text' : 'password'} placeholder="Secret Access Key"
                value={awsSecretKey} onChange={e => setAwsSecretKey(e.target.value)}
                className="input text-xs w-full pr-8" />
              <button onClick={() => setShowSecret(!showSecret)}
                className="absolute right-2 top-1/2 -translate-y-1/2"
                style={{ color: 'var(--color-text-tertiary)' }}>
                {showSecret ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
            <input type="text" placeholder="Session Token (optional, for temp credentials)"
              value={awsSessionToken} onChange={e => setAwsSessionToken(e.target.value)}
              className="input text-xs" />
          </div>
        )}
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 border-b" style={{ borderColor: 'var(--color-section-border)' }}>
        {[
          { id: 'overview' as Tab, Icon: BarChart3, label: 'Cost Overview' },
          { id: 'forecast' as Tab, Icon: TrendingUp, label: 'Forecast' },
          { id: 'rightsizing' as Tab, Icon: Lightbulb, label: 'Rightsizing' },
        ].map(({ id, Icon, label }) => (
          <button key={id} onClick={() => setTab(id)}
            className="flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-all"
            style={{
              borderBottom: tab === id ? '2px solid var(--color-accent)' : '2px solid transparent',
              color: tab === id ? 'var(--color-accent)' : 'var(--color-text-tertiary)',
            }}>
            <Icon size={15} />
            {label}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-2 p-4 rounded-lg"
          style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
          <AlertTriangle size={16} color="#ef4444" style={{ marginTop: 2, flexShrink: 0 }} />
          <p style={{ color: '#ef4444', fontSize: '0.85rem' }}>{error}</p>
        </div>
      )}

      {/* ─── Cost Overview Tab ─────────────────────────────────── */}
      {tab === 'overview' && (
        <div className="space-y-6">
          {!costData && (
            <div className="card p-5 text-center space-y-4">
              <BarChart3 size={40} style={{ color: 'var(--color-text-tertiary)', margin: '0 auto' }} />
              <div>
                <p className="font-semibold">Fetch AWS Cost Data</p>
                <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.82rem', marginTop: 4 }}>
                  Retrieve your last 30 days of AWS spending from Cost Explorer.
                  Requires <code style={{ background: 'var(--color-section-bg)', padding: '1px 5px', borderRadius: 3 }}>ce:GetCostAndUsage</code> permission.
                </p>
              </div>
              <button onClick={fetchCostData} disabled={loading}
                className="btn-primary flex items-center gap-2 mx-auto">
                {loading ? <RefreshCw size={15} className="animate-spin" /> : <BarChart3 size={15} />}
                {loading ? 'Fetching...' : 'Load Cost Data'}
              </button>
            </div>
          )}

          {costData && !costData.available && (
            <div className="card p-5 text-center">
              <AlertTriangle size={24} color="#f59e0b" style={{ margin: '0 auto 8px' }} />
              <p className="font-semibold">Cost Explorer Unavailable</p>
              <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.82rem', marginTop: 4 }}>
                {costData.reason || 'Cost Explorer is not enabled for this account.'}
              </p>
              <button onClick={() => setCostData(null)} className="btn-ghost mt-4">
                Try Again
              </button>
            </div>
          )}

          {costData?.available && (
            <>
              {/* Summary cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="card" style={{ padding: '16px 20px', textAlign: 'center' }}>
                  <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.75rem', fontWeight: 600 }}>
                    Total ({costData.period?.days}d)
                  </p>
                  <p style={{ color: 'var(--color-accent)', fontSize: '1.4rem', fontWeight: 700, marginTop: 4 }}>
                    ${costData.total_spend?.toFixed(2)}
                  </p>
                </div>
                <div className="card" style={{ padding: '16px 20px', textAlign: 'center' }}>
                  <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.75rem', fontWeight: 600 }}>
                    Avg Daily
                  </p>
                  <p style={{ color: 'var(--color-accent)', fontSize: '1.4rem', fontWeight: 700, marginTop: 4 }}>
                    ${costData.average_daily_cost?.toFixed(2)}
                  </p>
                </div>
                <div className="card" style={{ padding: '16px 20px', textAlign: 'center' }}>
                  <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.75rem', fontWeight: 600 }}>
                    Projected Monthly
                  </p>
                  <p style={{ color: '#10b981', fontSize: '1.4rem', fontWeight: 700, marginTop: 4 }}>
                    ${costData.projected_monthly_cost?.toFixed(2)}
                  </p>
                </div>
                <div className="card" style={{ padding: '16px 20px', textAlign: 'center' }}>
                  <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.75rem', fontWeight: 600 }}>
                    Projected Annual
                  </p>
                  <p style={{ color: '#f59e0b', fontSize: '1.4rem', fontWeight: 700, marginTop: 4 }}>
                    ${costData.projected_annual_cost?.toFixed(2)}
                  </p>
                </div>
              </div>

              {/* Daily cost chart */}
              {costData.daily_costs && costData.daily_costs.length > 0 && (
                <div className="card p-4">
                  <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-secondary)' }}>
                    Daily Cost Trend
                  </h3>
                  <div className="flex items-end gap-1" style={{ height: 120, overflowX: 'auto', minWidth: '100%' }}>
                    {costData.daily_costs.map((day: CostExplorerDay, i: number) => (
                      <div key={i} className="flex-1 flex flex-col items-center gap-1 min-w-[24px]" title={`${day.date}: $${day.total.toFixed(2)}`}>
                        <div style={{
                          width: '100%', height: `${(day.total / maxDailyCost) * 100}%`,
                          minHeight: 4, background: day.total > (costData.average_daily_cost || 0) * 1.2
                            ? '#ef4444' : 'var(--color-accent)',
                          borderRadius: '2px 2px 0 0', transition: 'height 0.3s ease',
                        }} />
                        {i % 5 === 0 && (
                          <span style={{ fontSize: '0.55rem', color: 'var(--color-text-tertiary)', whiteSpace: 'nowrap' }}>
                            {day.date.slice(5)}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Top services */}
              {costData.top_services && costData.top_services.length > 0 && (
                <div className="card p-4">
                  <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-secondary)' }}>
                    Top Services by Cost
                  </h3>
                  <div className="space-y-2">
                    {costData.top_services.map((svc: CostExplorerService) => (
                      <div key={svc.name}>
                        <div className="flex items-center justify-between text-sm mb-1">
                          <span className="truncate">{svc.name}</span>
                          <div className="flex items-center gap-3 flex-shrink-0">
                            <span style={{ color: 'var(--color-text-tertiary)', fontSize: '0.72rem' }}>
                              {svc.percentage}%
                            </span>
                            <span className="font-semibold" style={{ width: 80, textAlign: 'right' }}>
                              ${svc.total.toFixed(2)}
                            </span>
                          </div>
                        </div>
                        <div style={{
                          height: 4, background: 'var(--color-section-bg)',
                          borderRadius: 2, overflow: 'hidden',
                        }}>
                          <div style={{
                            height: '100%', width: `${Math.min(svc.percentage, 100)}%`,
                            background: svc.percentage > 30 ? '#ef4444' : svc.percentage > 10 ? '#f59e0b' : 'var(--color-accent)',
                            borderRadius: 2, transition: 'width 0.3s ease',
                          }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Cost Variation */}
              <div className="card p-4">
                <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-secondary)' }}>
                  Cost Variation Over Time
                </h3>
                {!variation && (
                  <div className="text-center py-4">
                    <button onClick={fetchVariation} disabled={loading}
                      className="btn-ghost flex items-center gap-2 mx-auto text-sm">
                      {loading ? <RefreshCw size={13} className="animate-spin" /> : <TrendingDown size={13} />}
                      Load Multi-Period Analysis
                    </button>
                  </div>
                )}
                {variation && !variation.available && (
                  <p style={{ color: '#f59e0b', fontSize: '0.78rem' }}>{variation.reason}</p>
                )}
                {variation?.available && variation.periods && (
                  <div className="space-y-4">
                    {/* Period totals */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                      {Object.entries(variation.periods).map(([key, period]) => (
                        <div key={key} className="card" style={{ padding: '10px 14px', textAlign: 'center' }}>
                          <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.65rem', fontWeight: 600 }}>
                            {key.replace('_', ' ')}
                          </p>
                          <p style={{ color: 'var(--color-accent)', fontSize: '1.1rem', fontWeight: 700, marginTop: 2 }}>
                            ${(period as CostVariationPeriod).total_cost.toFixed(0)}
                          </p>
                        </div>
                      ))}
                    </div>

                    {/* Changes */}
                    {variation.changes && Object.keys(variation.changes).length > 0 && (
                      <div className="space-y-1">
                        <p style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--color-text-secondary)' }}>
                          Period-over-Period Changes
                        </p>
                        {Object.entries(variation.changes).map(([key, change]) => (
                          <div key={key} className="flex items-center justify-between text-sm py-1">
                            <span style={{ color: 'var(--color-text-tertiary)', fontSize: '0.78rem' }}>
                              {key.replace('_', ' ')}
                            </span>
                            <span style={{
                              color: (change as CostVariationChange).change_percentage > 0 ? '#ef4444' : '#10b981',
                              fontWeight: 600,
                            }}>
                              {(change as CostVariationChange).change_percentage > 0 ? '+' : ''}
                              {(change as CostVariationChange).change_percentage}%
                            </span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Per-period top services */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {Object.entries(variation.periods).map(([key, period]) => (
                        <div key={key} className="card p-3">
                          <p className="font-semibold text-xs mb-2" style={{ color: 'var(--color-text-secondary)' }}>
                            {key.replace('_', ' ')} — Top Services
                          </p>
                          {((period as CostVariationPeriod).top_services || []).map((svc, j) => (
                            <div key={j} className="flex items-center justify-between text-xs py-0.5">
                              <span className="truncate">{svc.name}</span>
                              <span style={{ color: 'var(--color-text-tertiary)' }}>
                                ${svc.total.toFixed(0)} ({svc.percentage}%)
                              </span>
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <button onClick={() => setCostData(null)} className="btn-ghost text-sm">
                Clear & Refetch
              </button>
            </>
          )}
        </div>
      )}

      {/* ─── Forecast Tab ──────────────────────────────────────── */}
      {tab === 'forecast' && (
        <div className="space-y-6">
          {!forecast && (
            <div className="card p-5 text-center space-y-4">
              <TrendingUp size={40} style={{ color: 'var(--color-text-tertiary)', margin: '0 auto' }} />
              <div>
                <p className="font-semibold">90-Day Cost Forecast</p>
                <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.82rem', marginTop: 4 }}>
                  Predict your AWS spending for the next 3 months using Cost Explorer forecasting.
                </p>
              </div>
              <button onClick={fetchForecast} disabled={loading}
                className="btn-primary flex items-center gap-2 mx-auto">
                {loading ? <RefreshCw size={15} className="animate-spin" /> : <TrendingUp size={15} />}
                {loading ? 'Fetching...' : 'Load Forecast'}
              </button>
            </div>
          )}

          {forecast && !forecast.available && (
            <div className="card p-5 text-center">
              <AlertTriangle size={24} color="#f59e0b" style={{ margin: '0 auto 8px' }} />
              <p className="font-semibold">Forecast Unavailable</p>
              <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.82rem', marginTop: 4 }}>
                {forecast.reason || 'Forecasting is not available.'}
              </p>
              <button onClick={() => setForecast(null)} className="btn-ghost mt-4">Try Again</button>
            </div>
          )}

          {forecast?.available && forecast.forecasts && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {forecast.forecasts.map((f, i) => (
                  <div key={i} className="card" style={{ padding: '16px 20px', textAlign: 'center' }}>
                    <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.75rem', fontWeight: 600 }}>
                      {f.period.Start} – {f.period.End}
                    </p>
                    <p style={{ color: 'var(--color-accent)', fontSize: '1.4rem', fontWeight: 700, marginTop: 4 }}>
                      ${f.mean.toFixed(2)}
                    </p>
                  </div>
                ))}
              </div>

              {/* Simple bar chart for forecast */}
              <div className="card p-4">
                <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-secondary)' }}>
                  Forecasted Monthly Costs
                </h3>
                <div className="flex items-end gap-4" style={{ height: 160 }}>
                  {forecast.forecasts.map((f, i) => {
                    const maxForecast = Math.max(...forecast.forecasts!.map(x => x.mean), 0.01)
                    return (
                      <div key={i} className="flex-1 flex flex-col items-center gap-2">
                        <div style={{
                          width: '100%', maxWidth: 120,
                          height: `${(f.mean / maxForecast) * 100}%`,
                          minHeight: 20,
                          background: 'linear-gradient(180deg, var(--color-accent), #6366f1)',
                          borderRadius: '4px 4px 0 0',
                          display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
                          paddingTop: 6,
                        }}>
                          <span style={{ fontSize: '0.7rem', fontWeight: 600, color: '#fff' }}>
                            ${f.mean.toFixed(0)}
                          </span>
                        </div>
                        <span style={{ fontSize: '0.65rem', color: 'var(--color-text-tertiary)', textAlign: 'center' }}>
                          {f.period.Start}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>

              <button onClick={() => setForecast(null)} className="btn-ghost text-sm">Clear & Refetch</button>
            </div>
          )}
        </div>
      )}

      {/* ─── Rightsizing Tab ────────────────────────────────────── */}
      {tab === 'rightsizing' && (
        <div className="space-y-6">
          {!rightsizing && (
            <div className="card p-5 text-center space-y-4">
              <Lightbulb size={40} style={{ color: 'var(--color-text-tertiary)', margin: '0 auto' }} />
              <div>
                <p className="font-semibold">EC2 Rightsizing Recommendations</p>
                <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.82rem', marginTop: 4 }}>
                  Get recommendations for right-sizing your EC2 instances based on actual utilization.
                  Requires <code style={{ background: 'var(--color-section-bg)', padding: '1px 5px', borderRadius: 3 }}>ce:GetRightsizingRecommendation</code> permission.
                </p>
              </div>
              <button onClick={fetchRightsizing} disabled={loading}
                className="btn-primary flex items-center gap-2 mx-auto">
                {loading ? <RefreshCw size={15} className="animate-spin" /> : <Lightbulb size={15} />}
                {loading ? 'Fetching...' : 'Load Recommendations'}
              </button>
            </div>
          )}

          {rightsizing && rightsizing.length === 0 && (
            <div className="card p-5 text-center">
              <p className="font-semibold">No Recommendations</p>
              <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.82rem', marginTop: 4 }}>
                No rightsizing recommendations found. This could mean your instances are already optimally sized.
              </p>
            </div>
          )}

          {rightsizing && rightsizing.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                  {rightsizing.length} Recommendation{rightsizing.length !== 1 ? 's' : ''}
                </h3>
                <span className="badge-high" style={{ fontSize: '0.65rem' }}>
                  Save ${rightsizing.reduce((s, r) => s + r.estimated_monthly_savings, 0).toFixed(2)}/mo
                </span>
              </div>
              {rightsizing.map((rec, i) => (
                <div key={i} className="card" style={{ padding: '14px 18px' }}>
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-sm truncate">{rec.resource_id}</p>
                      <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.72rem' }}>
                        {rec.current_instance_type} → <span style={{ color: '#10b981' }}>{rec.recommended_instance_type || 'N/A'}</span>
                        {rec.rightsizing_type && <span> ({rec.rightsizing_type})</span>}
                      </p>
                    </div>
                    <div style={{ textAlign: 'right', flexShrink: 0 }}>
                      {rec.estimated_monthly_savings > 0 && (
                        <span className="badge-high" style={{ fontSize: '0.65rem' }}>
                          -${rec.estimated_monthly_savings.toFixed(2)}/mo
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
              <button onClick={() => setRightsizing(null)} className="btn-ghost text-sm">Clear & Refetch</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}