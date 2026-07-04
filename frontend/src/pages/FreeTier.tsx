import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Search, RefreshCw, Cloud, Server, Database, HardDrive,
  Network, Brain, Shield, BarChart3, CheckCircle, XCircle, AlertTriangle, Clock
} from 'lucide-react'
import { freeTier as freeTierApi, freeTierUsage } from '../api'

interface FreeTierService {
  service: string; full_name: string; type: string; category: string
  monthly_limit: string; description: string; beyond_free_tier: string
}

interface ServiceUsage {
  used: number; limit: number; unit: string; type: string; percentage: number
  remaining: number; status: 'ok' | 'warning' | 'exceeded'; details: any[]
}

interface UsageData {
  provider: string; timestamp: string
  summary: { total_services: number; within_limit: number; warning: number; exceeded: number; health_score: number }
  services: Record<string, ServiceUsage>
}

type Provider = 'aws' | 'azure' | 'gcp'

const PROVIDER_META: Record<Provider, { label: string; color: string; bg: string }> = {
  aws:   { label: 'AWS',   color: '#FF9900', bg: 'rgba(255,153,0,0.15)' },
  azure: { label: 'Azure', color: '#0078D4', bg: 'rgba(0,120,212,0.15)' },
  gcp:   { label: 'GCP',   color: '#34A853', bg: 'rgba(52,168,83,0.15)' },
}

const TYPE_META: Record<string, { label: string; color: string }> = {
  'always-free': { label: 'Always Free', color: '#10b981' },
  '12-month': { label: '12-Month Free', color: '#f59e0b' },
  'free-trial': { label: 'Free Trial', color: '#6366f1' },
  'not-free': { label: 'Not Free', color: '#ef4444' },
}

const CAT_ICONS: Record<string, React.ReactNode> = {
  compute: <Server size={14} />, storage: <HardDrive size={14} />, databases: <Database size={14} />,
  networking: <Network size={14} />, messaging: <Cloud size={14} />, analytics: <BarChart3 size={14} />,
  ai_ml: <Brain size={14} />, security: <Shield size={14} />, management: <BarChart3 size={14} />,
}

export default function FreeTier() {
  const navigate = useNavigate()
  const [provider, setProvider] = useState<Provider>('aws')
  const [tab, setTab] = useState<'usage' | 'reference'>('usage')
  const [tierData, setTierData] = useState<Record<string, FreeTierService[]> | null>(null)
  const [usageData, setUsageData] = useState<UsageData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true); setError(''); setExpanded(null); setSearch('')
    Promise.all([
      freeTierApi.get(provider).catch(() => null),
      freeTierUsage.get(provider).catch(() => null),
    ]).then(([tierRes, usageRes]) => {
      if (tierRes) {
        const pd = (tierRes as Record<string, Record<string, FreeTierService[]>>)[provider]
        setTierData(pd || null)
      }
      if (usageRes && !(usageRes as any).error) {
        setUsageData(usageRes as UsageData)
      }
    }).catch(e => setError(e.message)).finally(() => setLoading(false))
  }, [provider])

  const healthColor = (score: number) => score >= 80 ? '#10b981' : score >= 50 ? '#f59e0b' : '#ef4444'
  const usageBarColor = (pct: number) => pct < 50 ? '#10b981' : pct < 80 ? '#f59e0b' : '#ef4444'
  const statusIcon = (s: string) => s === 'ok' ? <CheckCircle size={12} style={{ color: '#10b981' }} /> :
    s === 'warning' ? <AlertTriangle size={12} style={{ color: '#f59e0b' }} /> :
    <XCircle size={12} style={{ color: '#ef4444' }} />

  const allServices: FreeTierService[] = []
  if (tierData) {
    for (const svcs of Object.values(tierData)) {
      for (const s of svcs) {
        if (!search || s.service.toLowerCase().includes(search.toLowerCase()) ||
            s.full_name.toLowerCase().includes(search.toLowerCase()) ||
            s.description.toLowerCase().includes(search.toLowerCase())) {
          allServices.push(s)
        }
      }
    }
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="btn-ghost flex items-center gap-1.5 text-sm">
          <ArrowLeft size={15} /> Back
        </button>
        <button onClick={() => { setLoading(true); freeTierUsage.get(provider).then(r => { if (!(r as any).error) setUsageData(r as UsageData) }).finally(() => setLoading(false)) }}
          className="btn-ghost flex items-center gap-1.5 text-sm" disabled={loading}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {/* Title */}
      <div className="card" style={{ borderLeft: '3px solid #6366f1', paddingLeft: '14px' }}>
        <h1 className="text-xl font-bold text-white">Free Tier</h1>
        <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.82em', marginTop: '2px' }}>
          Track usage and explore free tier services across AWS, Azure, and GCP
        </p>
      </div>

      {/* Provider selector */}
      <div className="grid grid-cols-3 gap-3">
        {(Object.keys(PROVIDER_META) as Provider[]).map(p => {
          const m = PROVIDER_META[p]; const active = provider === p
          return (
            <button key={p} onClick={() => setProvider(p)}
              className="flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-all"
              style={{ background: active ? m.bg : 'var(--color-section-bg)', border: `2px solid ${active ? m.color + 'cc' : 'var(--color-section-border)'}`, color: active ? m.color : 'var(--color-text-secondary)' }}>
              <Cloud size={16} /> {m.label}
            </button>
          )
        })}
      </div>

      {/* Tab switcher */}
      <div className="flex gap-2 p-1 rounded-xl" style={{ background: 'var(--color-section-bg)' }}>
        {[
          { id: 'usage' as const, label: 'My Usage', icon: <BarChart3 size={14} /> },
          { id: 'reference' as const, label: 'All Services', icon: <Cloud size={14} /> },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition-all"
            style={{ background: tab === t.id ? 'var(--color-card-bg)' : 'transparent', color: tab === t.id ? '#fff' : 'var(--color-text-tertiary)', boxShadow: tab === t.id ? '0 2px 8px rgba(0,0,0,0.2)' : 'none' }}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {loading && (
        <div className="card animate-pulse space-y-3">
          {[1, 2, 3].map(i => <div key={i} className="h-16 rounded-xl" style={{ background: 'var(--color-section-bg)' }} />)}
        </div>
      )}

      {error && <div className="card flex items-center gap-3 text-red-400"><AlertTriangle size={20} /> {error}</div>}

      {!loading && !error && tab === 'usage' && usageData && (
        <>
          {/* Health score + summary */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="card text-center py-4">
              <p className="text-3xl font-bold" style={{ color: healthColor(usageData.summary.health_score) }}>{usageData.summary.health_score}%</p>
              <p className="text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>Health Score</p>
            </div>
            <div className="card text-center py-4">
              <p className="text-2xl font-bold" style={{ color: '#10b981' }}>{usageData.summary.within_limit}</p>
              <p className="text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>Within Limit</p>
            </div>
            <div className="card text-center py-4">
              <p className="text-2xl font-bold" style={{ color: '#f59e0b' }}>{usageData.summary.warning}</p>
              <p className="text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>Warning</p>
            </div>
            <div className="card text-center py-4">
              <p className="text-2xl font-bold" style={{ color: '#ef4444' }}>{usageData.summary.exceeded}</p>
              <p className="text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>Exceeded</p>
            </div>
          </div>

          {/* Service usage list */}
          <div className="card space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-white text-sm">Service Usage</h2>
              <span className="text-xs flex items-center gap-1" style={{ color: 'var(--color-text-tertiary)' }}>
                <Clock size={11} /> Updated {new Date(usageData.timestamp).toLocaleTimeString()}
              </span>
            </div>
            {Object.entries(usageData.services).map(([service, usage]) => {
              const expanded_ = expanded === service
              const barC = usageBarColor(usage.percentage)
              return (
                <div key={service} className="rounded-xl overflow-hidden" style={{
                  border: `1px solid ${expanded_ ? barC + '40' : 'var(--color-section-border)'}`,
                  background: expanded_ ? 'var(--color-section-bg)' : 'transparent',
                }}>
                  <div className="flex items-center justify-between p-3 cursor-pointer" onClick={() => setExpanded(expanded_ ? null : service)}>
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <span style={{ color: barC }}>{CAT_ICONS[service] || <Cloud size={14} />}</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-white uppercase">{service}</span>
                          {statusIcon(usage.status)}
                        </div>
                        <span className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
                          {usage.type} - {(usage.limit || 0).toLocaleString()} {usage.unit} limit
                        </span>
                      </div>
                    </div>
                    <div className="text-right ml-4 flex-shrink-0">
                      <p className="text-sm font-semibold" style={{ color: barC }}>{(usage.percentage || 0).toFixed(1)}%</p>
                      <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>{(usage.remaining || 0).toLocaleString()} left</p>
                    </div>
                  </div>
                  <div className="px-3 pb-3">
                    <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--color-section-bg)' }}>
                      <div className="h-full rounded-full transition-all" style={{ width: `${Math.min(usage.percentage, 100)}%`, background: barC }} />
                    </div>
                    <div className="flex justify-between text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>
                      <span>{(usage.used || 0).toLocaleString()} used</span>
                      <span>{(usage.limit || 0).toLocaleString()} limit</span>
                    </div>
                  </div>
                  {expanded_ && (usage.details || []).length > 0 && (
                    <div className="px-3 pb-3 space-y-1" style={{ borderTop: '1px solid var(--color-section-border)', paddingTop: '8px' }}>
                      {(usage.details || []).slice(0, 5).map((d: any, i: number) => (
                        <div key={i} className="flex items-center justify-between p-2 rounded text-xs" style={{ background: 'var(--color-card-bg)' }}>
                          <span className="text-white truncate">{d.name || 'Unnamed'}</span>
                          <div className="flex items-center gap-2">
                            {d.is_free_tier && <span style={{ color: '#10b981', fontSize: '0.6rem', padding: '1px 5px', background: 'rgba(16,185,129,0.1)', borderRadius: '4px' }}>FREE</span>}
                            {d.state && <span style={{ color: d.state === 'running' ? '#10b981' : '#64748b', fontSize: '0.6rem' }}>{d.state}</span>}
                          </div>
                        </div>
                      ))}
                      {(usage.details || []).length > 5 && <p className="text-xs text-center" style={{ color: 'var(--color-text-tertiary)' }}>+{(usage.details || []).length - 5} more</p>}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}

      {!loading && !error && tab === 'reference' && (
        <>
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--color-text-tertiary)' }} />
            <input type="text" placeholder="Search services..." value={search} onChange={e => setSearch(e.target.value)} className="input w-full pl-9 text-sm" />
          </div>

          <div className="space-y-2">
            {allServices.length === 0 && <div className="card text-center py-8 text-sm" style={{ color: 'var(--color-text-tertiary)' }}>No services found</div>}
            {allServices.map((s, i) => {
              const meta = TYPE_META[s.type] || TYPE_META['not-free']
              const isExpanded = expanded === s.service + i
              return (
                <div key={i} className="rounded-xl overflow-hidden" style={{
                  border: `1px solid ${isExpanded ? meta.color + '40' : 'var(--color-section-border)'}`,
                  background: isExpanded ? 'var(--color-section-bg)' : 'transparent',
                }}>
                  <div className="flex items-center justify-between p-3 cursor-pointer" onClick={() => setExpanded(isExpanded ? null : s.service + i)}>
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <span style={{ color: meta.color }}>{CAT_ICONS[s.category] || <Cloud size={14} />}</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-white">{s.full_name || s.service}</span>
                          <span style={{ fontSize: '0.6rem', padding: '1px 6px', borderRadius: '4px', color: meta.color, background: meta.color + '15', fontWeight: 600 }}>{meta.label}</span>
                        </div>
                        <p className="text-xs truncate" style={{ color: 'var(--color-text-tertiary)' }}>{s.monthly_limit}</p>
                      </div>
                    </div>
                  </div>
                  {isExpanded && (
                    <div className="px-3 pb-3 space-y-2 text-xs" style={{ borderTop: '1px solid var(--color-section-border)', paddingTop: '8px' }}>
                      <p style={{ color: 'var(--color-text-secondary)' }}>{s.description}</p>
                      <p style={{ color: 'var(--color-text-tertiary)' }}><strong>Beyond free tier:</strong> {s.beyond_free_tier}</p>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}

      {!loading && !error && tab === 'usage' && !usageData && (
        <div className="card text-center py-12" style={{ color: 'var(--color-text-tertiary)' }}>
          <Cloud size={40} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">No usage data available</p>
          <p className="text-xs mt-1">Run a cloud scan first to see your free tier usage</p>
        </div>
      )}
    </div>
  )
}
