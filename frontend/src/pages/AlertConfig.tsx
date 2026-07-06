import { useCallback, useEffect, useState } from 'react'
import {
  Bell, Mail, Slack, Webhook, RefreshCw, AlertTriangle,
  CheckCircle, Clock, Eye, EyeOff,
} from 'lucide-react'
import { alerts as alertsApi } from '../api'
import type { AlertConfig, AlertHistoryItem } from '../types'

const NOTIFY_OPTIONS = [
  { value: 'anomaly', label: 'Cost Anomalies' },
  { value: 'budget', label: 'Budget Thresholds' },
  { value: 'scan_complete', label: 'Scan Complete' },
]

const SEVERITY_COLORS: Record<string, string> = {
  high: '#ef4444',
  medium: '#f59e0b',
  low: '#3b82f6',
}

function fmt(iso: string) {
  if (!iso) return '—'
  const d = new Date(iso)
  return isNaN(d.getTime()) ? '—' : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export default function AlertConfigPage() {
  const [config, setConfig] = useState<AlertConfig>({ email: null, slack_webhook: null, notify_on: ['anomaly'] })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [showSlack, setShowSlack] = useState(false)
  const [history, setHistory] = useState<AlertHistoryItem[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)

  const loadConfig = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const c = await alertsApi.getConfig()
      setConfig(c)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load config')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadHistory = useCallback(async () => {
    setLoadingHistory(true)
    try {
      const { history: h } = await alertsApi.history(50)
      setHistory(h)
    } catch { /* ignore */ }
    finally { setLoadingHistory(false) }
  }, [])

  useEffect(() => { loadConfig(); loadHistory() }, [loadConfig, loadHistory])

  const toggleNotify = (value: string) => {
    setConfig((prev) => ({
      ...prev,
      notify_on: prev.notify_on.includes(value)
        ? prev.notify_on.filter((v) => v !== value)
        : [...prev.notify_on, value],
    }))
  }

  const handleSave = async () => {
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const updated = await alertsApi.updateConfig({
        email: config.email || null,
        slack_webhook: config.slack_webhook || null,
        notify_on: config.notify_on,
      })
      setConfig(updated)
      setSuccess('Alert configuration saved.')
      setTimeout(() => setSuccess(''), 3000)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setError('')
    setSuccess('')
    try {
      await alertsApi.test()
      setSuccess('Test notification sent! Check your configured channels.')
      setTimeout(() => setSuccess(''), 5000)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Test failed')
    } finally {
      setTesting(false)
    }
  }

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-8 space-y-4">
        {[1, 2, 3].map((n) => (
          <div key={n} className="card" style={{ padding: '18px 20px' }}>
            <div className="h-5 rounded w-32" style={{ background: 'var(--color-section-bg)' }} />
            <div className="h-9 rounded w-full mt-3" style={{ background: 'var(--color-section-bg)' }} />
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Alert Configuration</h1>
          <p className="text-sm mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>
            Configure notification channels for cost alerts and anomaly reports
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleTest} disabled={testing}
            className="btn-ghost text-sm flex items-center gap-1">
            {testing ? <RefreshCw size={13} className="animate-spin" /> : <Bell size={13} />}
            Test
          </button>
        </div>
      </div>

      {error && (
        <div className="card flex items-center gap-3 text-red-400">
          <AlertTriangle size={16} /> {error}
        </div>
      )}

      {success && (
        <div className="card flex items-center gap-3" style={{ color: '#10b981', borderColor: 'rgba(16,185,129,0.3)' }}>
          <CheckCircle size={16} /> {success}
        </div>
      )}

      {/* Email */}
      <div className="card" style={{ padding: '18px 20px' }}>
        <div className="flex items-center gap-2 mb-3">
          <Mail size={15} style={{ color: 'var(--color-text-tertiary)' }} />
          <h2 className="font-semibold text-white text-sm">Email Notification</h2>
          <span className="text-xs ml-1" style={{ color: 'var(--color-text-tertiary)' }}>
            — Cloudflare Email Routing or SMTP
          </span>
        </div>
        <input className="input w-full text-sm"
          placeholder="you@example.com"
          value={config.email || ''}
          onChange={(e) => setConfig((prev) => ({ ...prev, email: e.target.value || null }))} />
        <p className="text-xs mt-1.5" style={{ color: 'var(--color-text-tertiary)' }}>
          Leave blank to disable email alerts.
        </p>
      </div>

      {/* Slack Webhook */}
      <div className="card" style={{ padding: '18px 20px' }}>
        <div className="flex items-center gap-2 mb-3">
          <Slack size={15} style={{ color: 'var(--color-text-tertiary)' }} />
          <h2 className="font-semibold text-white text-sm">Slack Webhook</h2>
        </div>
        <div className="relative">
          <input type={showSlack ? 'text' : 'password'} className="input w-full text-sm font-mono"
            placeholder="https://hooks.slack.com/services/T00/B00/xxxxx"
            value={config.slack_webhook || ''}
            onChange={(e) => setConfig((prev) => ({ ...prev, slack_webhook: e.target.value || null }))} />
          <button onClick={() => setShowSlack(!showSlack)}
            className="absolute right-2.5 top-1/2 -translate-y-1/2"
            style={{ color: 'var(--color-text-tertiary)' }}>
            {showSlack ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        </div>
        <p className="text-xs mt-1.5" style={{ color: 'var(--color-text-tertiary)' }}>
          Leave blank to disable Slack alerts.
        </p>
      </div>

      {/* Notification Types */}
      <div className="card" style={{ padding: '18px 20px' }}>
        <div className="flex items-center gap-2 mb-3">
          <Bell size={15} style={{ color: 'var(--color-text-tertiary)' }} />
          <h2 className="font-semibold text-white text-sm">Notify On</h2>
        </div>
        <div className="space-y-2">
          {NOTIFY_OPTIONS.map((opt) => {
            const sel = config.notify_on.includes(opt.value)
            return (
              <label key={opt.value}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-all"
                style={{
                  background: sel ? 'rgba(59,130,246,0.08)' : 'var(--color-section-bg)',
                  border: `1px solid ${sel ? 'rgba(59,130,246,0.3)' : 'var(--color-section-border)'}`,
                }}>
                <input type="checkbox" checked={sel}
                  onChange={() => toggleNotify(opt.value)} className="shrink-0" />
                <span className="text-sm font-medium text-white">{opt.label}</span>
              </label>
            )
          })}
        </div>
      </div>

      {/* Save */}
      <button onClick={handleSave} disabled={saving}
        className="btn-primary w-full py-3 flex items-center justify-center gap-2">
        {saving ? <RefreshCw size={16} className="animate-spin" /> : null}
        {saving ? 'Saving…' : 'Save Configuration'}
      </button>

      {/* Alert History */}
      <div className="pt-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <Clock size={16} /> Alert History
          </h2>
          <button onClick={loadHistory} disabled={loadingHistory}
            className="btn-ghost text-xs flex items-center gap-1">
            <RefreshCw size={12} className={loadingHistory ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>

        {loadingHistory ? (
          <div className="space-y-2">
            {[1, 2, 3].map((n) => (
              <div key={n} className="card" style={{ padding: '14px 16px' }}>
                <div className="h-4 rounded w-48" style={{ background: 'var(--color-section-bg)' }} />
                <div className="h-3 rounded w-32 mt-2" style={{ background: 'var(--color-section-bg)' }} />
              </div>
            ))}
          </div>
        ) : history.length === 0 ? (
          <div className="card text-center py-8" style={{ color: 'var(--color-text-tertiary)' }}>
            <Bell size={24} className="mx-auto mb-2 opacity-40" />
            <p className="text-xs">No alerts sent yet</p>
          </div>
        ) : (
          <div className="card p-0 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--color-card-border)', background: 'rgba(102,126,234,0.06)' }}>
                    {(['Date', 'Type', 'Title', 'Severity', 'Channel'] as const).map((h) => (
                      <th key={h} className="px-4 py-3 font-semibold text-xs uppercase tracking-wider text-left"
                        style={{ color: 'var(--color-text-secondary)', whiteSpace: 'nowrap' }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {history.map((item) => (
                    <tr key={item.id}
                      style={{ borderBottom: '1px solid var(--color-card-border)' }}>
                      <td className="px-4 py-3 whitespace-nowrap text-xs"
                        style={{ color: 'var(--color-text-tertiary)' }}>
                        {fmt(item.sent_at)}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className="text-xs font-medium">{item.alert_type}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-sm text-white">{item.title}</span>
                        {item.message && (
                          <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-tertiary)' }}>
                            {item.message}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className="text-xs px-2 py-0.5 rounded-full font-medium"
                          style={{
                            background: `${SEVERITY_COLORS[item.severity] || '#6b7280'}20`,
                            color: SEVERITY_COLORS[item.severity] || '#6b7280',
                            border: `1px solid ${(SEVERITY_COLORS[item.severity] || '#6b7280')}40`,
                          }}>
                          {item.severity}
                        </span>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-xs"
                        style={{ color: 'var(--color-text-tertiary)' }}>
                        {item.channel || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
