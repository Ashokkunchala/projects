import { useRef, useState } from 'react'
import {
  Code, Github, Upload, DollarSign, TrendingDown,
  AlertTriangle, CheckCircle, FileJson, FileText, BarChart3,
  Lightbulb, ExternalLink, Copy, RefreshCw, X, File,
} from 'lucide-react'
import { estimate } from '../api'
import type { CostEstimateReport, ResourceEstimate, CostEstimateSuggestion, FreeTierLimit, FreeTierAnalysis } from '../api'

type Tab = 'paste' | 'git' | 'upload' | 'results'

type FormatOption = 'auto' | 'terraform' | 'cloudformation' | 'json' | 'yaml'

const FORMAT_LABELS: Record<string, string> = {
  auto: 'Auto Detect',
  terraform: 'Terraform (.tf)',
  cloudformation: 'CloudFormation (JSON/YAML)',
  json: 'JSON',
  yaml: 'YAML',
}

function ProviderIcon({ provider }: { provider: string }) {
  const colors: Record<string, string> = { aws: '#FF9900', azure: '#0078D4', gcp: '#4285F4' }
  return (
    <span style={{
      background: colors[provider] || '#888',
      borderRadius: '4px', padding: '1px 6px',
      fontSize: '0.65rem', fontWeight: 800, color: '#fff',
      letterSpacing: '0.5px',
    }}>
      {provider.toUpperCase()}
    </span>
  )
}

function CostCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="card" style={{ padding: '16px 20px', textAlign: 'center' }}>
      <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.75rem', fontWeight: 600, letterSpacing: '0.03em' }}>
        {label}
      </p>
      <p style={{ color, fontSize: '1.6rem', fontWeight: 700, marginTop: 4, letterSpacing: '-0.02em' }}>
        {value}
      </p>
    </div>
  )
}

function SuggestionCard({ suggestion }: { suggestion: CostEstimateSuggestion }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(suggestion.action).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }).catch(() => {})
  }

  return (
    <div className="card" style={{ padding: '16px 20px' }}>
      <div className="flex items-start gap-3">
        <div style={{
          background: 'rgba(16,185,129,0.12)', borderRadius: '8px',
          padding: '6px', flexShrink: 0,
        }}>
          <Lightbulb size={16} color="#10b981" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-sm">{suggestion.title}</span>
            {suggestion.potential_savings > 0 && (
              <span className="badge-high" style={{ fontSize: '0.65rem' }}>
                -${suggestion.potential_savings.toFixed(2)}/mo
              </span>
            )}
          </div>
          <p style={{ color: 'var(--color-text-secondary)', fontSize: '0.8rem', marginTop: 4 }}>
            {suggestion.description}
          </p>
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <code style={{
              background: 'var(--color-section-bg)', borderRadius: '4px',
              padding: '2px 8px', fontSize: '0.72rem', color: 'var(--color-text-secondary)',
              border: '1px solid var(--color-section-border)',
              flex: '1 1 auto', minWidth: 0, overflow: 'auto',
            }}>
              {suggestion.action}
            </code>
            <button onClick={copy} className="btn-ghost" style={{ padding: '2px 8px', flexShrink: 0 }}>
              {copied ? <CheckCircle size={13} color="#10b981" /> : <Copy size={13} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function ResourceRow({ resource }: { resource: ResourceEstimate }) {
  return (
    <div className="card" style={{ padding: '12px 16px' }}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-sm truncate">{resource.resource_name}</p>
          <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.72rem' }}>
            <code style={{ background: 'var(--color-section-bg)', padding: '1px 5px', borderRadius: 3, fontSize: '0.7rem' }}>
              {resource.resource_type}
            </code>
            {resource.instance_type && (
              <span> — {resource.instance_type}</span>
            )}
            {resource.details && (
              <span style={{ marginLeft: 4 }}>— {resource.details}</span>
            )}
          </p>
          {resource.estimate_note && (
            <p style={{ color: '#f59e0b', fontSize: '0.7rem', marginTop: 2 }}>
              {resource.estimate_note}
            </p>
          )}
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <p className="font-bold" style={{ color: 'var(--color-accent)' }}>
            ${resource.monthly_cost.toFixed(2)}
          </p>
          <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.68rem' }}>/mo</p>
        </div>
      </div>
    </div>
  )
}

export default function Estimate() {
  const [tab, setTab] = useState<Tab>('paste')
  const [pasteContent, setPasteContent] = useState('')
  const [pasteFormat, setPasteFormat] = useState<FormatOption>('auto')
  const [gitUrl, setGitUrl] = useState('')
  const [gitBranch, setGitBranch] = useState('')
  const [uploadFiles, setUploadFiles] = useState<File[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [report, setReport] = useState<CostEstimateReport | null>(null)
  const [inputFormat, setInputFormat] = useState('')
  const [inputProvider, setInputProvider] = useState('')
  const [suggestionFilter, setSuggestionFilter] = useState<'all' | 'savings'>('all')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handlePaste = async () => {
    if (!pasteContent.trim()) return
    setLoading(true)
    setError('')
    try {
      const res = await estimate.paste(pasteContent, pasteFormat)
      setReport(res.report)
      setInputFormat(res.format)
      setInputProvider(res.provider)
      setTab('results')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Estimation failed')
    } finally {
      setLoading(false)
    }
  }

  const handleGit = async () => {
    if (!gitUrl.trim()) return
    setLoading(true)
    setError('')
    try {
      const branch = gitBranch.trim() || undefined
      const res = await estimate.git(gitUrl, branch)
      setReport(res.report)
      setInputFormat('git')
      setInputProvider(res.provider || '')
      setTab('results')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Git estimation failed')
    } finally {
      setLoading(false)
    }
  }

  const handleUpload = async () => {
    if (uploadFiles.length === 0) return
    setLoading(true)
    setError('')
    try {
      const res = await estimate.upload(uploadFiles)
      setReport(res.report)
      setInputFormat('upload')
      setInputProvider(res.provider || '')
      setTab('results')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Upload estimation failed')
    } finally {
      setLoading(false)
    }
  }

  const handleReset = () => {
    setReport(null)
    setError('')
    setTab('paste')
    setPasteContent('')
    setGitUrl('')
    setUploadFiles([])
  }

  const displayFormat = inputFormat === 'git' ? 'Git Repository' : inputFormat === 'upload' ? 'Uploaded Files' : FORMAT_LABELS[inputFormat] || inputFormat

  const sortedSuggestions = report?.suggestions
    ? [...report.suggestions].sort((a, b) => {
        if (suggestionFilter === 'savings') return b.potential_savings - a.potential_savings
        return 0
      })
    : []

  const breakdownEntries = report?.top_services_by_cost || []

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-8">

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Cost Estimator</h1>
        <p style={{ color: 'var(--color-text-secondary)', fontSize: '0.88rem', marginTop: 4 }}>
          Estimate cloud costs before deploying — from Terraform, CloudFormation, or your Git repo.
          Get instant cost breakdowns, alternative suggestions, and optimization tips.
        </p>
      </div>

      {/* Input Section — only show when no report yet */}
      {!report && (
        <>
          {/* Tab bar */}
          <div className="flex gap-1 border-b" style={{ borderColor: 'var(--color-section-border)' }}>
            {[
              { id: 'paste' as Tab, Icon: Code, label: 'Paste Template' },
              { id: 'git' as Tab, Icon: Github, label: 'Git Repository' },
              { id: 'upload' as Tab, Icon: Upload, label: 'Upload Files' },
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

          {tab === 'paste' && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 flex-wrap">
                <span style={{ fontSize: '0.78rem', color: 'var(--color-text-tertiary)' }}>Format:</span>
                {(['auto', 'terraform', 'cloudformation', 'json'] as FormatOption[]).map(f => (
                  <button key={f} onClick={() => setPasteFormat(f)}
                    className="text-xs font-medium px-2.5 py-1 rounded transition-all"
                    style={{
                      background: pasteFormat === f ? 'var(--color-accent)' : 'var(--color-section-bg)',
                      color: pasteFormat === f ? '#fff' : 'var(--color-text-secondary)',
                      border: '1px solid var(--color-section-border)',
                    }}>
                    {FORMAT_LABELS[f]}
                  </button>
                ))}
              </div>

              <textarea
                value={pasteContent}
                onChange={e => setPasteContent(e.target.value)}
                placeholder={`Paste your Terraform (.tf) or CloudFormation (JSON/YAML) template here...\n\ne.g.:\nresource "aws_instance" "web" {\n  ami           = "ami-0c55b159cbfafe1f0"\n  instance_type = "t3.micro"\n}`}
                style={{
                  width: '100%', minHeight: '280px', padding: '16px',
                  background: 'var(--color-section-bg)', border: '1px solid var(--color-section-border)',
                  borderRadius: '8px', color: 'var(--color-text)', fontFamily: 'monospace',
                  fontSize: '0.82rem', lineHeight: 1.5, resize: 'vertical',
                }}
              />

              <button onClick={handlePaste} disabled={loading || !pasteContent.trim()}
                className="btn-primary flex items-center gap-2">
                {loading ? <RefreshCw size={15} className="animate-spin" /> : <BarChart3 size={15} />}
                {loading ? 'Estimating...' : 'Estimate Cost'}
              </button>
            </div>
          )}

          {tab === 'git' && (
            <div className="space-y-4">
              <div className="card p-5 space-y-4">
                <div>
                  <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--color-text-secondary)' }}>
                    Git Repository URL
                  </label>
                  <input type="url" value={gitUrl} onChange={e => setGitUrl(e.target.value)}
                    placeholder="https://github.com/your-org/terraform-infra.git"
                    style={{
                      width: '100%', marginTop: 6, padding: '10px 14px',
                      background: 'var(--color-section-bg)', border: '1px solid var(--color-section-border)',
                      borderRadius: '6px', color: 'var(--color-text)', fontSize: '0.88rem',
                    }} />
                </div>
                <div>
                  <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--color-text-secondary)' }}>
                    Branch (optional)
                  </label>
                  <input type="text" value={gitBranch} onChange={e => setGitBranch(e.target.value)}
                    placeholder="main"
                    style={{
                      width: '100%', marginTop: 6, padding: '10px 14px',
                      background: 'var(--color-section-bg)', border: '1px solid var(--color-section-border)',
                      borderRadius: '6px', color: 'var(--color-text)', fontSize: '0.88rem',
                    }} />
                </div>
                <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.78rem' }}>
                  <Github size={12} style={{ display: 'inline', marginRight: 4 }} />
                  Public repos are supported. The repo will be shallow-cloned and parsed for Terraform/CloudFormation templates.
                </p>
                <button onClick={handleGit} disabled={loading || !gitUrl.trim()}
                  className="btn-primary flex items-center gap-2">
                  {loading ? <RefreshCw size={15} className="animate-spin" /> : <Github size={15} />}
                  {loading ? 'Cloning & Estimating...' : 'Estimate from Repo'}
                </button>
              </div>
            </div>
          )}

          {tab === 'upload' && (
            <div className="space-y-4"
              onDragOver={e => { e.preventDefault(); e.stopPropagation() }}
              onDrop={e => {
                e.preventDefault()
                e.stopPropagation()
                const droppedFiles = Array.from(e.dataTransfer.files)
                if (droppedFiles.length > 0) {
                  setUploadFiles(prev => {
                    const existing = new Set(prev.map(f => f.name + f.size))
                    const newFiles = droppedFiles.filter(f => !existing.has(f.name + f.size))
                    return [...prev, ...newFiles]
                  })
                }
              }}>
              <div className="card p-5 space-y-4">
                <div
                  onClick={() => fileInputRef.current?.click()}
                  style={{
                    border: '2px dashed var(--color-section-border)',
                    borderRadius: '8px', padding: '40px 20px',
                    textAlign: 'center', cursor: 'pointer',
                    transition: 'border-color 0.2s',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--color-accent)' }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--color-section-border)' }}>
                  <Upload size={32} style={{ color: 'var(--color-text-tertiary)', marginBottom: 8 }} />
                  <p className="font-semibold text-sm mb-1">Drop files here or click to browse</p>
                  <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.78rem' }}>
                    Supports .tf, .json, .yaml, .yml, .template files and .zip archives
                  </p>
                  <input ref={fileInputRef} type="file" multiple
                    accept=".tf,.json,.yaml,.yml,.template,.zip,application/zip"
                    onChange={e => {
                      const selectedFiles = Array.from(e.target.files || [])
                      setUploadFiles(prev => {
                        const existing = new Set(prev.map(f => f.name + f.size))
                        const newFiles = selectedFiles.filter(f => !existing.has(f.name + f.size))
                        return [...prev, ...newFiles]
                      })
                      e.target.value = ''
                    }}
                    style={{ display: 'none' }} />
                </div>

                {uploadFiles.length > 0 && (
                  <div className="space-y-1">
                    <p style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--color-text-secondary)' }}>
                      Selected Files ({uploadFiles.length})
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {uploadFiles.map((f, i) => (
                        <div key={i} className="flex items-center gap-1.5 px-2 py-1 rounded"
                          style={{
                            background: 'var(--color-section-bg)',
                            border: '1px solid var(--color-section-border)',
                            fontSize: '0.75rem',
                          }}>
                          <File size={12} />
                          <span className="truncate" style={{ maxWidth: 200 }}>{f.name}</span>
                          <span style={{ color: 'var(--color-text-tertiary)', fontSize: '0.65rem' }}>
                            {(f.size / 1024).toFixed(0)} KB
                          </span>
                          <button onClick={() => setUploadFiles(prev => prev.filter((_, j) => j !== i))}
                            className="btn-ghost" style={{ padding: 0, lineHeight: 1 }}>
                            <X size={12} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <button onClick={handleUpload} disabled={loading || uploadFiles.length === 0}
                  className="btn-primary flex items-center gap-2">
                  {loading ? <RefreshCw size={15} className="animate-spin" /> : <Upload size={15} />}
                  {loading ? 'Uploading & Estimating...' : `Estimate from ${uploadFiles.length} file(s)`}
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Error */}
      {error && (
        <div className="flex items-start gap-2 p-4 rounded-lg"
          style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
          <AlertTriangle size={16} color="#ef4444" style={{ marginTop: 2, flexShrink: 0 }} />
          <p style={{ color: '#ef4444', fontSize: '0.85rem' }}>{error}</p>
        </div>
      )}

      {/* Results Section */}
      {report && (
        <div className="space-y-6">
          {/* Summary header */}
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-bold">Cost Estimate</h2>
              <span style={{
                background: 'var(--color-section-bg)', borderRadius: '4px',
                padding: '2px 8px', fontSize: '0.72rem',
                color: 'var(--color-text-secondary)', border: '1px solid var(--color-section-border)',
              }}>
                {displayFormat}
              </span>
              <ProviderIcon provider={inputProvider} />
            </div>
            <button onClick={handleReset} className="btn-ghost flex items-center gap-1.5 text-sm">
              <RefreshCw size={13} />
              New Estimate
            </button>
          </div>

          {/* Cost cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <CostCard label="Monthly Cost" value={`$${report.total_monthly_cost.toFixed(2)}`} color="var(--color-accent)" />
            <CostCard label="Yearly Cost" value={`$${report.total_yearly_cost.toFixed(2)}`} color="var(--color-accent)" />
            <CostCard label="Resources" value={String(report.resource_count)} color="var(--color-text)" />
            <CostCard label="Potential Savings" value={`-$${report.total_potential_savings.toFixed(2)}`} color="#10b981" />
          </div>

          {/* Provider breakdown */}
          {report.provider_breakdown && Object.keys(report.provider_breakdown).length > 1 && (
            <div className="card p-4 space-y-2">
              <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-secondary)' }}>Cost by Provider</h3>
              <div className="flex flex-wrap gap-3">
                {Object.entries(report.provider_breakdown).map(([provider, cost]) => (
                  <div key={provider} className="flex items-center gap-2">
                    <ProviderIcon provider={provider} />
                    <span className="font-semibold">${(cost as number).toFixed(2)}/mo</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Cost breakdown table */}
          {breakdownEntries.length > 0 && (
            <div className="card p-4">
              <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-secondary)' }}>
                Cost by Service
              </h3>
              <div className="space-y-2">
                {breakdownEntries.map((item) => (
                  <div key={item.service}>
                    <div className="flex items-center justify-between text-sm mb-1">
                      <span className="truncate">{item.service}</span>
                      <div className="flex items-center gap-3 flex-shrink-0">
                        <span style={{ color: 'var(--color-text-tertiary)', fontSize: '0.72rem' }}>
                          {item.percentage}%
                        </span>
                        <span className="font-semibold" style={{ width: 80, textAlign: 'right' }}>
                          ${item.monthly_cost.toFixed(2)}
                        </span>
                      </div>
                    </div>
                    <div style={{
                      height: 4, background: 'var(--color-section-bg)',
                      borderRadius: 2, overflow: 'hidden',
                    }}>
                      <div style={{
                        height: '100%', width: `${item.percentage}%`,
                        background: item.percentage > 30
                          ? '#ef4444'
                          : item.percentage > 10
                            ? '#f59e0b'
                            : 'var(--color-accent)',
                        borderRadius: 2, transition: 'width 0.3s ease',
                      }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Resource estimates */}
          {report.resource_estimates.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                  Resource Breakdown ({report.resource_estimates.length})
                </h3>
              </div>
              <div className="space-y-2">
                {report.resource_estimates.map((r, i) => (
                  <ResourceRow key={i} resource={r} />
                ))}
              </div>
            </div>
          )}

          {/* Unknown resources */}
          {report.unknown_resources.length > 0 && (
            <div className="card p-4" style={{ border: '1px solid rgba(245,158,11,0.3)' }}>
              <div className="flex items-center gap-2 mb-2">
                <AlertTriangle size={14} color="#f59e0b" />
                <span className="font-semibold text-sm">Unknown Resources ({report.unknown_resources.length})</span>
              </div>
              <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.78rem' }}>
                These resource types could not be estimated. Check the resource type or add pricing data.
              </p>
              <div className="mt-2 space-y-1">
                {report.unknown_resources.map((ur, i) => (
                  <div key={i} style={{ fontSize: '0.78rem', color: 'var(--color-text-secondary)' }}>
                    <code style={{ background: 'var(--color-section-bg)', padding: '1px 5px', borderRadius: 3 }}>
                      {ur.resource_type}
                    </code>
                    <span style={{ marginLeft: 4 }}>— {ur.resource_name}: {ur.reason}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Suggestions */}
          {sortedSuggestions.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                    Cost-Saving Suggestions ({sortedSuggestions.length})
                  </h3>
                  <span className="badge-high" style={{ fontSize: '0.65rem' }}>
                    Save ${report.total_potential_savings.toFixed(2)}/mo
                  </span>
                </div>
                <div className="flex gap-1">
                  <button onClick={() => setSuggestionFilter('all')}
                    className="text-xs px-2 py-1 rounded"
                    style={{
                      background: suggestionFilter === 'all' ? 'var(--color-accent)' : 'var(--color-section-bg)',
                      color: suggestionFilter === 'all' ? '#fff' : 'var(--color-text-secondary)',
                      border: '1px solid var(--color-section-border)',
                    }}>
                    All
                  </button>
                  <button onClick={() => setSuggestionFilter('savings')}
                    className="text-xs px-2 py-1 rounded"
                    style={{
                      background: suggestionFilter === 'savings' ? 'var(--color-accent)' : 'var(--color-section-bg)',
                      color: suggestionFilter === 'savings' ? '#fff' : 'var(--color-text-secondary)',
                      border: '1px solid var(--color-section-border)',
                    }}>
                    By Savings
                  </button>
                </div>
              </div>
              <div className="space-y-2">
                {sortedSuggestions.map((s, i) => (
                  <SuggestionCard key={i} suggestion={s} />
                ))}
              </div>
            </div>
          )}

          {/* ─── Free Tier Report ───────────────────────────────────────── */}
          {(report.free_tier_limits || report.free_tier_eligible?.length || report.free_resource_count > 0) && (
            <div className="card p-4" style={{ border: '1px solid rgba(16,185,129,0.25)' }}>
              <div className="flex items-center gap-2 mb-4">
                <CheckCircle size={16} color="#10b981" />
                <h2 className="text-base font-bold">Free Tier Report</h2>
                {report.free_tier_analysis && (
                  <span style={{
                    fontSize: '0.6rem', fontWeight: 700, padding: '2px 10px', borderRadius: '12px',
                    background: report.free_tier_analysis.within_limits
                      ? 'rgba(16,185,129,0.12)' : 'rgba(245,158,11,0.12)',
                    color: report.free_tier_analysis.within_limits ? '#10b981' : '#f59e0b',
                  }}>
                    {report.free_tier_analysis.within_limits ? 'Within Limits' : 'Exceeds Limits'}
                  </span>
                )}
              </div>

              {/* Summary stats */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
                <div className="card" style={{ padding: '10px 14px', textAlign: 'center' }}>
                  <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.65rem', fontWeight: 600 }}>Always-Free Resources</p>
                  <p style={{ color: '#10b981', fontSize: '1.3rem', fontWeight: 700 }}>{report.free_resource_count}</p>
                </div>
                <div className="card" style={{ padding: '10px 14px', textAlign: 'center' }}>
                  <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.65rem', fontWeight: 600 }}>Free Tier Eligible</p>
                  <p style={{ color: '#6366f1', fontSize: '1.3rem', fontWeight: 700 }}>{(report.free_tier_eligible || []).length}</p>
                </div>
                <div className="card" style={{ padding: '10px 14px', textAlign: 'center' }}>
                  <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.65rem', fontWeight: 600 }}>Billed Resources</p>
                  <p style={{ color: 'var(--color-accent)', fontSize: '1.3rem', fontWeight: 700 }}>
                    {report.resource_count - report.free_resource_count - (report.free_tier_eligible || []).length}
                  </p>
                </div>
                <div className="card" style={{ padding: '10px 14px', textAlign: 'center' }}>
                  <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.65rem', fontWeight: 600 }}>Monthly Free Savings</p>
                  <p style={{ color: '#f59e0b', fontSize: '1.1rem', fontWeight: 700, marginTop: 2 }}>
                    ${report.free_tier_eligible
                      ? report.free_tier_eligible.reduce((s, r) => s + r.monthly_cost, 0).toFixed(0)
                      : '0'}
                  </p>
                </div>
              </div>

              {/* Free tier eligible resources list */}
              {report.free_tier_eligible && report.free_tier_eligible.length > 0 && (
                <div className="mb-4">
                  <p className="font-semibold text-xs mb-2" style={{ color: 'var(--color-text-secondary)' }}>
                    Free Tier Eligible Resources
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {report.free_tier_eligible.map((r, i) => (
                      <div key={i} style={{
                        background: 'rgba(16,185,129,0.06)', borderRadius: '4px',
                        padding: '3px 10px', fontSize: '0.72rem',
                        border: '1px solid rgba(16,185,129,0.15)',
                      }}>
                        <code style={{ fontSize: '0.68rem', color: '#10b981' }}>{r.resource_type}</code>
                        <span style={{ marginLeft: 6, color: 'var(--color-text-secondary)' }}>{r.resource_name}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Per-service limit table */}
              {report.free_tier_limits && Object.keys(report.free_tier_limits).length > 0 && (
                <div>
                  <p className="font-semibold text-xs mb-2" style={{ color: 'var(--color-text-secondary)' }}>
                    Per-Service Free Tier Limits
                  </p>
                  <div className="space-y-1">
                    {Object.entries(report.free_tier_limits).map(([key, limit]) => (
                      <div key={key} className="flex items-center gap-2 py-1.5 border-b text-xs"
                        style={{ borderColor: 'var(--color-section-border)' }}>
                        <span style={{
                          fontSize: '0.55rem', fontWeight: 700, padding: '1px 5px', borderRadius: '3px', flexShrink: 0,
                          background: limit.type === 'always-free' ? 'rgba(16,185,129,0.10)' : 'rgba(99,102,241,0.10)',
                          color: limit.type === 'always-free' ? '#10b981' : '#6366f1',
                        }}>
                          {limit.type === 'always-free' ? '∞' : '12m'}
                        </span>
                        <span className="font-semibold" style={{ width: 90, flexShrink: 0 }}>{limit.name}</span>
                        <span className="truncate" style={{ color: 'var(--color-text-tertiary)', flex: 1, minWidth: 0 }}>
                          {limit.description}
                        </span>
                        <span style={{ color: 'var(--color-text-secondary)', flexShrink: 0, textAlign: 'right' }}>
                          {limit.annual_limit}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Info footer */}
          <div className="flex items-start gap-3 p-4 rounded-lg"
            style={{ background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.15)' }}>
            <Info size={16} color="var(--color-accent)" style={{ marginTop: 2, flexShrink: 0 }} />
            <div style={{ fontSize: '0.78rem', color: 'var(--color-text-tertiary)' }}>
              <p className="font-semibold mb-1" style={{ color: 'var(--color-text-secondary)' }}>How estimates work</p>
              <p>Prices are based on public on-demand rates for us-east-1 (AWS), East US (Azure), and us-central1 (GCP). Your actual costs may vary based on:</p>
              <ul className="list-disc ml-4 mt-1 space-y-0.5">
                <li>Region selection — different regions have different pricing</li>
                <li>Reserved/spot pricing — commitments can save 30-60%</li>
                <li>Discounts — enterprise agreements, volume discounts</li>
                <li>Data transfer — egress costs depend on usage patterns</li>
                <li>Dynamic resources — auto-scaling, Lambda invocations vary</li>
              </ul>
              <p className="mt-2">Use these estimates as a planning guide. Always verify with cloud provider pricing calculators before deploying.</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Info(props: { size: number; color: string; style?: React.CSSProperties }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={props.size} height={props.size} viewBox="0 0 24 24" fill="none" stroke={props.color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={props.style}>
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="16" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  )
}
