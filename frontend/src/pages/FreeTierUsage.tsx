import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, RefreshCw, AlertTriangle, CheckCircle, XCircle, Clock, TrendingUp, Cloud, Server, Database, HardDrive, Network, Brain, Shield } from 'lucide-react'
import { freeTierUsage } from '../api'

interface ServiceUsage {
  used: number
  limit: number
  unit: string
  type: string
  percentage: number
  remaining: number
  status: 'ok' | 'warning' | 'exceeded'
  details: ResourceDetail[]
}

interface ResourceDetail {
  name: string
  type?: string
  state?: string
  region?: string
  is_free_tier?: boolean
  estimated_hours?: number
}

interface UsageSummary {
  total_services: number
  within_limit: number
  warning: number
  exceeded: number
  health_score: number
}

interface UsageData {
  provider: string
  timestamp: string
  summary: UsageSummary
  services: Record<string, ServiceUsage>
}

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  ec2: <Server size={16} />,
  lambda: <Cloud size={16} />,
  s3: <HardDrive size={16} />,
  rds: <Database size={16} />,
  dynamodb: <Database size={16} />,
  ebs: <HardDrive size={16} />,
  elasticache: <Database size={16} />,
  cloudfront: <Network size={16} />,
  sqs: <Cloud size={16} />,
  sns: <Cloud size={16} />,
  route53: <Network size={16} />,
  kinesis: <Cloud size={16} />,
  glue: <Cloud size={16} />,
  athena: <Database size={16} />,
  ecr: <Cloud size={16} />,
}

const STATUS_CONFIG = {
  ok: { color: '#10b981', bg: 'rgba(16,185,129,0.1)', icon: <CheckCircle size={14} /> },
  warning: { color: '#f59e0b', bg: 'rgba(245,158,11,0.1)', icon: <AlertTriangle size={14} /> },
  exceeded: { color: '#ef4444', bg: 'rgba(239,68,68,0.1)', icon: <XCircle size={14} /> },
}

export default function FreeTierUsage() {
  const navigate = useNavigate()
  const [provider, setProvider] = useState('aws')
  const [data, setData] = useState<UsageData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expandedService, setExpandedService] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())

  const fetchData = async () => {
    setLoading(true)
    setError('')
    try {
      const result = await freeTierUsage.get(provider) as { error?: string } & UsageData
      if (result.error) {
        setError(result.error)
      } else {
        setData(result as UsageData)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch usage data')
    } finally {
      setLoading(false)
      setLastRefresh(new Date())
    }
  }

  useEffect(() => {
    fetchData()
  }, [provider])

  const getUsageBarColor = (percentage: number) => {
    if (percentage < 50) return '#10b981'
    if (percentage < 80) return '#f59e0b'
    return '#ef4444'
  }

  const getStatusIcon = (status: string) => {
    const config = STATUS_CONFIG[status as keyof typeof STATUS_CONFIG] || STATUS_CONFIG.ok
    return config.icon
  }

  const getStatusColor = (status: string) => {
    const config = STATUS_CONFIG[status as keyof typeof STATUS_CONFIG] || STATUS_CONFIG.ok
    return config.color
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="btn-ghost flex items-center gap-1.5 text-sm">
          <ArrowLeft size={15} /> Back
        </button>
        <button onClick={fetchData} className="btn-ghost flex items-center gap-1.5 text-sm" disabled={loading}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      <div className="card space-y-5">
        <div style={{ borderLeft: '3px solid #10b981', paddingLeft: '14px' }}>
          <h1 className="text-xl font-bold text-white">Real-Time Free Tier Usage</h1>
          <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.82em', marginTop: '2px' }}>
            Track your resource usage against free tier limits
          </p>
        </div>

        <div className="grid grid-cols-3 gap-3">
          {(['aws', 'azure', 'gcp'] as const).map((p) => (
            <button
              key={p}
              onClick={() => setProvider(p)}
              className="flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-all"
              style={{
                background: provider === p ? 'rgba(16,185,129,0.15)' : 'var(--color-section-bg)',
                border: `2px solid ${provider === p ? '#10b981cc' : 'var(--color-section-border)'}`,
                color: provider === p ? '#10b981' : 'var(--color-text-secondary)',
              }}
            >
              <Cloud size={16} />
              {p.toUpperCase()}
            </button>
          ))}
        </div>

        {data && (
          <div className="flex items-center gap-4 text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
            <span className="flex items-center gap-1">
              <Clock size={12} />
              Last updated: {lastRefresh.toLocaleTimeString()}
            </span>
            <span>Health Score: <span style={{ color: data.summary.health_score >= 80 ? '#10b981' : '#f59e0b', fontWeight: 600 }}>{data.summary.health_score}%</span></span>
          </div>
        )}
      </div>

      {loading && (
        <div className="card animate-pulse space-y-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-20 rounded-xl" style={{ background: 'var(--color-section-bg)' }} />
          ))}
        </div>
      )}

      {error && (
        <div className="card flex items-center gap-3 text-red-400">
          <AlertTriangle size={20} /> {error}
        </div>
      )}

      {!loading && !error && data && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'Total Services', value: data.summary.total_services, color: '#6366f1' },
              { label: 'Within Limit', value: data.summary.within_limit, color: '#10b981' },
              { label: 'Warning', value: data.summary.warning, color: '#f59e0b' },
              { label: 'Exceeded', value: data.summary.exceeded, color: '#ef4444' },
            ].map(({ label, value, color }) => (
              <div key={label} className="card text-center py-4">
                <p className="text-2xl font-bold" style={{ color }}>{value}</p>
                <p className="text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>{label}</p>
              </div>
            ))}
          </div>

          <div className="card space-y-4">
            <h2 className="font-semibold text-white">Service Usage</h2>
            <div className="space-y-3">
              {Object.entries(data.services).map(([service, usage]) => {
                const isExpanded = expandedService === service
                const barColor = getUsageBarColor(usage.percentage)
                const statusColor = getStatusColor(usage.status)

                return (
                  <div
                    key={service}
                    className="rounded-xl overflow-hidden transition-all"
                    style={{
                      border: `1px solid ${isExpanded ? barColor + '40' : 'var(--color-section-border)'}`,
                      background: isExpanded ? 'var(--color-section-bg)' : 'transparent',
                    }}
                  >
                    <div
                      className="flex items-center justify-between p-4 cursor-pointer"
                      onClick={() => setExpandedService(isExpanded ? null : service)}
                    >
                      <div className="flex items-center gap-3 flex-1 min-w-0">
                        <span style={{ color: barColor }}>{CATEGORY_ICONS[service] || <Cloud size={16} />}</span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-semibold text-white uppercase">{service}</p>
                            <span style={{ color: statusColor }}>{getStatusIcon(usage.status)}</span>
                          </div>
                          <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-tertiary)' }}>
                            {usage.type} • {usage.limit.toLocaleString()} {usage.unit} limit
                          </p>
                        </div>
                      </div>
                      <div className="text-right ml-4 flex-shrink-0">
                        <p className="text-sm font-semibold" style={{ color: barColor }}>{usage.percentage.toFixed(1)}%</p>
                        <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
                          {usage.remaining.toLocaleString()} {usage.unit} left
                        </p>
                      </div>
                    </div>

                    <div className="px-4 pb-4">
                      <div className="h-2 rounded-full overflow-hidden" style={{ background: 'var(--color-section-bg)' }}>
                        <div
                          className="h-full rounded-full transition-all"
                          style={{ width: `${Math.min(usage.percentage, 100)}%`, background: barColor }}
                        />
                      </div>
                      <div className="flex justify-between text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>
                        <span>{usage.used.toLocaleString()} {usage.unit} used</span>
                        <span>{usage.limit.toLocaleString()} {usage.unit} limit</span>
                      </div>
                    </div>

                    {isExpanded && usage.details.length > 0 && (
                      <div className="px-4 pb-4 space-y-2" style={{ borderTop: '1px solid var(--color-section-border)', paddingTop: '12px' }}>
                        <p className="text-xs font-medium mb-2" style={{ color: 'var(--color-text-tertiary)' }}>Resources</p>
                        {usage.details.slice(0, 5).map((detail, idx) => (
                          <div key={idx} className="flex items-center justify-between p-2 rounded-lg text-xs" style={{ background: 'var(--color-card-bg)', border: '1px solid var(--color-section-border)' }}>
                            <span className="font-medium text-white truncate">{detail.name || 'Unnamed'}</span>
                            <div className="flex items-center gap-2">
                              {detail.is_free_tier && (
                                <span style={{ color: '#10b981', fontSize: '0.65rem', padding: '2px 6px', background: 'rgba(16,185,129,0.1)', borderRadius: '4px' }}>FREE TIER</span>
                              )}
                              {detail.state && (
                                <span style={{ color: detail.state === 'running' ? '#10b981' : '#64748b', fontSize: '0.65rem' }}>{detail.state}</span>
                              )}
                            </div>
                          </div>
                        ))}
                        {usage.details.length > 5 && (
                          <p className="text-xs text-center" style={{ color: 'var(--color-text-tertiary)' }}>
                            +{usage.details.length - 5} more resources
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
