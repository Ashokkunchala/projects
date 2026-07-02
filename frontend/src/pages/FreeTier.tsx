import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Search, Cloud, Server, Database, HardDrive, Network, Brain, Shield, BarChart3, CheckCircle, XCircle, AlertTriangle, ExternalLink } from 'lucide-react'
import { freeTier as freeTierApi } from '../api'

interface FreeTierService {
  service: string
  full_name: string
  type: 'always-free' | '12-month' | 'free-trial' | 'not-free'
  category: string
  monthly_limit: string
  annual_limit?: string
  description: string
  beyond_free_tier: string
  notes?: string
  instance_types?: string
  engines?: string
  types?: string
  additional_limits?: Record<string, string>
}

interface ProviderData {
  compute?: FreeTierService[]
  storage?: FreeTierService[]
  databases?: FreeTierService[]
  networking?: FreeTierService[]
  messaging?: FreeTierService[]
  analytics?: FreeTierService[]
  ai_ml?: FreeTierService[]
  security?: FreeTierService[]
  management?: FreeTierService[]
}

type Provider = 'aws' | 'azure' | 'gcp'
type Category = 'compute' | 'storage' | 'databases' | 'networking' | 'messaging' | 'analytics' | 'ai_ml' | 'security' | 'management'

const PROVIDER_META: Record<Provider, { label: string; color: string; bg: string }> = {
  aws:   { label: 'AWS',   color: '#FF9900', bg: 'rgba(255,153,0,0.15)' },
  azure: { label: 'Azure', color: '#0078D4', bg: 'rgba(0,120,212,0.15)' },
  gcp:   { label: 'GCP',   color: '#34A853', bg: 'rgba(52,168,83,0.15)' },
}

const CATEGORY_META: Record<Category, { label: string; icon: React.ReactNode; color: string }> = {
  compute:    { label: 'Compute',    icon: <Server size={16} />,        color: '#6366f1' },
  storage:    { label: 'Storage',    icon: <HardDrive size={16} />,     color: '#8b5cf6' },
  databases:  { label: 'Databases',  icon: <Database size={16} />,      color: '#06b6d4' },
  networking: { label: 'Networking', icon: <Network size={16} />,       color: '#10b981' },
  messaging:  { label: 'Messaging',  icon: <Cloud size={16} />,         color: '#f59e0b' },
  analytics:  { label: 'Analytics',  icon: <BarChart3 size={16} />,     color: '#3b82f6' },
  ai_ml:      { label: 'AI / ML',    icon: <Brain size={16} />,         color: '#ec4899' },
  security:   { label: 'Security',   icon: <Shield size={16} />,        color: '#ef4444' },
  management: { label: 'Management', icon: <BarChart3 size={16} />,     color: '#14b8a6' },
}

const TYPE_META: Record<string, { label: string; color: string; bg: string }> = {
  'always-free': { label: 'Always Free', color: '#10b981', bg: 'rgba(16,185,129,0.15)' },
  '12-month':    { label: '12-Month Free', color: '#f59e0b', bg: 'rgba(245,158,11,0.15)' },
  'free-trial':  { label: 'Free Trial', color: '#6366f1', bg: 'rgba(99,102,241,0.15)' },
  'not-free':    { label: 'Not Free', color: '#ef4444', bg: 'rgba(239,68,68,0.15)' },
}

export default function FreeTier() {
  const navigate = useNavigate()
  const [provider, setProvider] = useState<Provider>('aws')
  const [data, setData] = useState<ProviderData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [expandedService, setExpandedService] = useState<string | null>(null)
  const [selectedCategories, setSelectedCategories] = useState<Category[]>([])

  useEffect(() => {
    setLoading(true)
    setError('')
    freeTierApi.get(provider)
      .then((res) => {
        const providerData = (res as Record<string, ProviderData>)[provider]
        setData(providerData)
      })
      .catch((err) => setError(err.message || 'Failed to load free tier data'))
      .finally(() => setLoading(false))
  }, [provider])

  const categories = data ? (Object.keys(data) as Category[]) : []
  const filteredCategories = selectedCategories.length > 0
    ? categories.filter(c => selectedCategories.includes(c))
    : categories

  const filterServices = (services: FreeTierService[]) => {
    if (!search) return services
    const q = search.toLowerCase()
    return services.filter(s =>
      s.service.toLowerCase().includes(q) ||
      s.full_name.toLowerCase().includes(q) ||
      s.description.toLowerCase().includes(q) ||
      s.monthly_limit.toLowerCase().includes(q)
    )
  }

  const getServiceIcon = (type: string) => {
    if (type === 'always-free') return <CheckCircle size={14} style={{ color: '#10b981' }} />
    if (type === 'not-free') return <XCircle size={14} style={{ color: '#ef4444' }} />
    return <AlertTriangle size={14} style={{ color: '#f59e0b' }} />
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="btn-ghost flex items-center gap-1.5 text-sm">
          <ArrowLeft size={15} /> Back
        </button>
      </div>

      <div className="card space-y-5">
        <div style={{ borderLeft: '3px solid #6366f1', paddingLeft: '14px' }} className="flex items-center gap-3">
          <div style={{
            width: '40px', height: '40px', borderRadius: '12px',
            background: 'linear-gradient(135deg, rgba(99,102,241,0.2), rgba(139,92,246,0.2))',
            border: '1px solid rgba(99,102,241,0.25)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Cloud size={20} style={{ color: '#6366f1' }} />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white" style={{ letterSpacing: '-0.01em' }}>
              Cloud Free Tier Reference
            </h1>
            <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.82em', marginTop: '2px' }}>
              Complete guide to free tier services, limits, and usage across AWS, Azure, and GCP
            </p>
          </div>
        </div>

        {/* Provider selector */}
        <div className="grid grid-cols-3 gap-3">
          {(Object.keys(PROVIDER_META) as Provider[]).map((p) => {
            const meta = PROVIDER_META[p]
            const active = provider === p
            return (
              <button
                key={p}
                onClick={() => setProvider(p)}
                className="flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-all"
                style={{
                  background: active ? meta.bg : 'var(--color-section-bg)',
                  border: `2px solid ${active ? meta.color + 'cc' : 'var(--color-section-border)'}`,
                  color: active ? meta.color : 'var(--color-text-secondary)',
                  transform: active ? 'scale(1.02)' : 'scale(1)',
                }}
              >
                <Cloud size={16} />
                {meta.label}
              </button>
            )
          })}
        </div>

        {/* Search and filter */}
        <div className="flex flex-wrap gap-3">
          <div className="flex-1 min-w-[200px] relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--color-text-tertiary)' }} />
            <input
              type="text"
              placeholder="Search services..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="input w-full pl-9 text-sm"
            />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {categories.map((cat) => {
              const meta = CATEGORY_META[cat]
              const active = selectedCategories.includes(cat)
              return (
                <button
                  key={cat}
                  onClick={() => {
                    setSelectedCategories(prev =>
                      active ? prev.filter(c => c !== cat) : [...prev, cat]
                    )
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
                  style={{
                    background: active ? meta.color + '20' : 'var(--color-section-bg)',
                    border: `1px solid ${active ? meta.color + '60' : 'var(--color-section-border)'}`,
                    color: active ? meta.color : 'var(--color-text-secondary)',
                  }}
                >
                  {meta.icon}
                  {meta.label}
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="card animate-pulse space-y-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-24 rounded-xl" style={{ background: 'var(--color-section-bg)' }} />
          ))}
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="card flex items-center gap-3 text-red-400">
          <AlertTriangle size={20} /> {error}
        </div>
      )}

      {/* Free tier content */}
      {!loading && !error && data && (
        <div className="space-y-6">
          {/* Summary stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {(() => {
              let alwaysFree = 0
              let twelveMonth = 0
              let total = 0
              let totalServices = 0
              for (const cat of Object.values(data)) {
                for (const svc of cat || []) {
                  totalServices++
                  total++
                  if (svc.type === 'always-free') alwaysFree++
                  if (svc.type === '12-month') twelveMonth++
                }
              }
              return [
                { label: 'Total Services', value: total, color: '#6366f1' },
                { label: 'Always Free', value: alwaysFree, color: '#10b981' },
                { label: '12-Month Free', value: twelveMonth, color: '#f59e0b' },
                { label: 'Categories', value: Object.keys(data).length, color: '#8b5cf6' },
              ]
            })().map(({ label, value, color }) => (
              <div key={label} className="card text-center py-4">
                <p className="text-2xl font-bold" style={{ color }}>{value}</p>
                <p className="text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>{label}</p>
              </div>
            ))}
          </div>

          {/* Category sections */}
          {filteredCategories.map((cat) => {
            const services = filterServices(data[cat] || [])
            if (services.length === 0) return null
            const meta = CATEGORY_META[cat]
            return (
              <div key={cat} className="card space-y-4">
                <div className="flex items-center gap-2" style={{ borderBottom: `2px solid ${meta.color}30`, paddingBottom: '10px' }}>
                  <span style={{ color: meta.color }}>{meta.icon}</span>
                  <h2 className="font-semibold text-white">{meta.label}</h2>
                  <span className="text-xs ml-2" style={{ color: 'var(--color-text-tertiary)' }}>
                    ({services.length} service{services.length !== 1 ? 's' : ''})
                  </span>
                </div>

                <div className="space-y-3">
                  {services.map((svc) => {
                    const typeMeta = TYPE_META[svc.type] || TYPE_META['not-free']
                    const isExpanded = expandedService === `${cat}-${svc.service}`
                    return (
                      <div
                        key={svc.service}
                        className="rounded-xl overflow-hidden transition-all"
                        style={{
                          border: `1px solid ${isExpanded ? meta.color + '40' : 'var(--color-section-border)'}`,
                          background: isExpanded ? 'var(--color-section-bg)' : 'transparent',
                        }}
                      >
                        {/* Service header */}
                        <div
                          className="flex items-center justify-between p-4 cursor-pointer"
                          onClick={() => setExpandedService(isExpanded ? null : `${cat}-${svc.service}`)}
                        >
                          <div className="flex items-center gap-3 flex-1 min-w-0">
                            {getServiceIcon(svc.type)}
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <p className="text-sm font-semibold text-white">{svc.service}</p>
                                <span style={{
                                  fontSize: '0.65rem',
                                  padding: '2px 6px',
                                  borderRadius: '4px',
                                  background: typeMeta.bg,
                                  color: typeMeta.color,
                                  border: `1px solid ${typeMeta.color}30`,
                                  fontWeight: 600,
                                }}>
                                  {typeMeta.label}
                                </span>
                              </div>
                              <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-tertiary)' }}>
                                {svc.full_name}
                              </p>
                            </div>
                          </div>
                          <div className="text-right ml-4 flex-shrink-0">
                            <p className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                              {svc.monthly_limit}
                            </p>
                          </div>
                        </div>

                        {/* Expanded details */}
                        {isExpanded && (
                          <div className="px-4 pb-4 space-y-3" style={{ borderTop: '1px solid var(--color-section-border)', paddingTop: '12px' }}>
                            <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
                              {svc.description}
                            </p>

                            {/* Limits grid */}
                            <div className="grid grid-cols-2 gap-2">
                              <div className="rounded-lg p-3" style={{ background: 'var(--color-card-bg)', border: '1px solid var(--color-section-border)' }}>
                                <p className="text-xs font-medium" style={{ color: 'var(--color-text-tertiary)' }}>Monthly Limit</p>
                                <p className="text-sm font-semibold text-white mt-1">{svc.monthly_limit}</p>
                              </div>
                              {svc.annual_limit && (
                                <div className="rounded-lg p-3" style={{ background: 'var(--color-card-bg)', border: '1px solid var(--color-section-border)' }}>
                                  <p className="text-xs font-medium" style={{ color: 'var(--color-text-tertiary)' }}>Annual Limit</p>
                                  <p className="text-sm font-semibold text-white mt-1">{svc.annual_limit}</p>
                                </div>
                              )}
                            </div>

                            {/* Additional limits */}
                            {svc.additional_limits && Object.keys(svc.additional_limits).length > 0 && (
                              <div className="rounded-lg p-3" style={{ background: 'var(--color-card-bg)', border: '1px solid var(--color-section-border)' }}>
                                <p className="text-xs font-medium mb-2" style={{ color: 'var(--color-text-tertiary)' }}>Additional Limits</p>
                                <div className="space-y-1">
                                  {Object.entries(svc.additional_limits).map(([key, val]) => (
                                    <div key={key} className="flex justify-between text-xs">
                                      <span style={{ color: 'var(--color-text-secondary)' }}>{key.replace(/_/g, ' ')}</span>
                                      <span className="font-medium text-white">{val}</span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Instance types */}
                            {svc.instance_types && (
                              <div className="rounded-lg p-3" style={{ background: 'var(--color-card-bg)', border: '1px solid var(--color-section-border)' }}>
                                <p className="text-xs font-medium" style={{ color: 'var(--color-text-tertiary)' }}>Eligible Types</p>
                                <p className="text-sm text-white mt-1">{svc.instance_types}</p>
                              </div>
                            )}

                            {/* Beyond free tier */}
                            <div className="rounded-lg p-3" style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.15)' }}>
                              <p className="text-xs font-medium" style={{ color: '#f87171' }}>Cost Beyond Free Tier</p>
                              <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>{svc.beyond_free_tier}</p>
                            </div>

                            {/* Notes */}
                            {svc.notes && (
                              <div className="rounded-lg p-3" style={{ background: 'rgba(99,102,241,0.05)', border: '1px solid rgba(99,102,241,0.15)' }}>
                                <p className="text-xs font-medium" style={{ color: '#a5b4fc' }}>Note</p>
                                <p className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>{svc.notes}</p>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}

          {/* Links section */}
          <div className="card">
            <h3 className="font-semibold text-white mb-3">Official Free Tier Pages</h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {[
                { provider: 'AWS', url: 'https://aws.amazon.com/free/', color: '#FF9900' },
                { provider: 'Azure', url: 'https://azure.microsoft.com/en-us/pricing/free-services/', color: '#0078D4' },
                { provider: 'GCP', url: 'https://cloud.google.com/free', color: '#34A853' },
              ].map(({ provider: p, url, color }) => (
                <a
                  key={p}
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 p-3 rounded-lg transition-all"
                  style={{
                    background: color + '10',
                    border: `1px solid ${color}30`,
                  }}
                >
                  <Cloud size={14} style={{ color }} />
                  <span className="text-sm font-medium" style={{ color }}>{p} Free Tier</span>
                  <ExternalLink size={12} style={{ color: 'var(--color-text-tertiary)', marginLeft: 'auto' }} />
                </a>
              ))}
            </div>
          </div>

          {/* Tips */}
          <div className="card" style={{ background: 'linear-gradient(135deg, var(--color-card-bg) 0%, rgba(99,102,241,0.04) 100%)' }}>
            <h3 className="font-semibold text-white mb-3">Free Tier Tips</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {[
                { title: 'Always Free = No Expiration', desc: 'Services marked "Always Free" never expire. Perfect for personal projects and learning.' },
                { title: '12-Month Free = Time-Limited', desc: 'These services are free for 12 months from account creation. Set reminders to downgrade or delete.' },
                { title: 'Monitor Usage', desc: 'Set up billing alerts at 80% and 100% of free tier limits to avoid unexpected charges.' },
                { title: 'Clean Up Resources', desc: 'Delete unused instances, volumes, and snapshots before your 12-month period expires.' },
              ].map(({ title, desc }) => (
                <div key={title} className="rounded-lg p-3" style={{ background: 'var(--color-section-bg)', border: '1px solid var(--color-section-border)' }}>
                  <p className="text-xs font-semibold text-white">{title}</p>
                  <p className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>{desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
