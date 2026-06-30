import { useState, useEffect, useCallback } from 'react'
import { Lightbulb, ChevronDown, X, Sparkles } from 'lucide-react'

const TIPS = [
  {
    title: 'New to AWS Cloud?',
    body: 'Start scanning just 2-3 regions (like us-east-1, eu-west-1) and a few core services (EC2, S3, RDS). The rule engine works without any AI key.',
    icon: '🚀',
  },
  {
    title: 'Free Tier Gotchas',
    body: 't2.micro/t3.micro are free for 12 months — but EBS volumes, Elastic IPs, and NAT Gateways are NOT. The tool flags these hidden costs for you.',
    icon: '🆓',
  },
  {
    title: 'Low-Cost Alternatives',
    body: 'Replace t2 instances with t3 (20% cheaper), gp2 volumes with gp3 (20% cheaper), and consider Graviton (t4g/m6g) for up to 40% savings.',
    icon: '💡',
  },
  {
    title: 'Reserved Instances',
    body: 'For steady workloads, 1-year Standard RIs save ~40% vs On-Demand. 3-year RIs save ~60%. Savings Plans are even more flexible.',
    icon: '📋',
  },
  {
    title: 'Spot Instances',
    body: 'For fault-tolerant or batch workloads, Spot Instances are 60-90% cheaper than On-Demand. Use them for EMR, Batch, or stateless apps.',
    icon: '⚡',
  },
  {
    title: 'S3 Storage Classes',
    body: 'Transition objects older than 30 days to S3 Infrequent Access (40% cheaper) and 90+ days to S3 Glacier (80% cheaper). Enable lifecycle rules!',
    icon: '🗄️',
  },
  {
    title: 'Right-Sizing 101',
    body: 'Most workloads use less than 20% of allocated resources. The tool checks for over-provisioned instances and recommends optimal sizes.',
    icon: '📏',
  },
  {
    title: 'Clean Up Regularly',
    body: 'Unattached EBS volumes, stale snapshots, unused Elastic IPs, and idle load balancers are the top 4 wasted resources. Scan monthly!',
    icon: '🧹',
  },
]

export default function SuggestionPanel() {
  const [expanded, setExpanded] = useState(false)
  const [dismissedTips, setDismissedTips] = useState<Set<number>>(new Set())
  const [currentTip, setCurrentTip] = useState(0)

  const nextTip = useCallback(() => {
    let next = (currentTip + 1) % TIPS.length
    let attempts = 0
    while (dismissedTips.has(next) && attempts < TIPS.length) {
      next = (next + 1) % TIPS.length
      attempts++
    }
    setCurrentTip(next)
  }, [currentTip, dismissedTips])

  useEffect(() => {
    if (expanded) return
    const id = setInterval(nextTip, 12000)
    return () => clearInterval(id)
  }, [expanded, nextTip])

  const tip = TIPS[currentTip]
  if (!tip) return null

  const dismiss = () => {
    const next = new Set(dismissedTips)
    next.add(currentTip)
    setDismissedTips(next)
    if (next.size >= TIPS.length) setDismissedTips(new Set())
    nextTip()
  }

  return (
    <div className="card" style={{
      position: 'relative',
      overflow: 'hidden',
      border: '1px solid rgba(99,102,241,0.15)',
      background: 'linear-gradient(135deg, var(--color-card-bg) 0%, rgba(99,102,241,0.04) 100%)',
    }}>
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, height: '2px',
        background: 'linear-gradient(90deg, transparent, #6366f1, transparent)',
      }} />

      {/* Header */}
      <div
        className="flex items-center justify-between cursor-pointer select-none"
        onClick={() => setExpanded(!expanded)}
        style={{ padding: '0 0 4px 0' }}
      >
        <div className="flex items-center gap-2">
          <div style={{
            width: '28px', height: '28px', borderRadius: '8px',
            background: 'linear-gradient(135deg, rgba(99,102,241,0.2), rgba(139,92,246,0.2))',
            border: '1px solid rgba(99,102,241,0.2)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Lightbulb size={14} style={{ color: '#6366f1' }} />
          </div>
          <span className="text-sm font-semibold text-white">Tips & Insights</span>
          <span style={{
            fontSize: '0.62rem', color: 'var(--color-text-tertiary)',
            background: 'var(--color-section-bg)', padding: '1px 6px',
            borderRadius: '4px', fontWeight: 600,
          }}>
            {dismissedTips.size < TIPS.length ? 'NEW' : 'ALL SEEN'}
          </span>
        </div>
        <ChevronDown size={14} style={{
          color: 'var(--color-text-tertiary)',
          transform: expanded ? 'rotate(180deg)' : 'none',
          transition: 'transform 0.2s',
        }} />
      </div>

      {/* Active tip */}
      <div style={{ minHeight: expanded ? '0' : '72px', transition: 'min-height 0.3s' }}>
        <div className="flex items-start gap-3 mt-1">
          <span style={{ fontSize: '1.3rem', lineHeight: 1, marginTop: '2px' }}>{tip.icon}</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-white mb-0.5">{tip.title}</p>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
              {tip.body}
            </p>
          </div>
          <button
            onClick={(e) => { e.stopPropagation(); dismiss() }}
            className="shrink-0 transition-colors"
            style={{ color: 'var(--color-text-tertiary)', padding: '2px' }}
            onMouseEnter={e => (e.currentTarget.style.color = '#f87171')}
            onMouseLeave={e => (e.currentTarget.style.color = 'var(--color-text-tertiary)')}
            title="Dismiss tip"
          >
            <X size={13} />
          </button>
        </div>
      </div>

      {/* Expanded: all tips */}
      {expanded && (
        <div className="mt-3 space-y-2" style={{ borderTop: '1px solid var(--color-section-border)', paddingTop: '12px' }}>
          <div className="flex items-center gap-1.5 mb-2">
            <Sparkles size={12} style={{ color: '#6366f1' }} />
            <span className="text-xs font-medium" style={{ color: 'var(--color-text-tertiary)' }}>
              Quick cost-saving knowledge
            </span>
          </div>
          {TIPS.map((t, i) => (
            <div key={i}
              className="flex items-start gap-2.5 px-2 py-1.5 rounded-lg text-xs cursor-pointer transition-all"
              style={{
                background: i === currentTip ? 'rgba(99,102,241,0.08)' : 'transparent',
                border: i === currentTip ? '1px solid rgba(99,102,241,0.15)' : '1px solid transparent',
              }}
              onClick={() => setCurrentTip(i)}
            >
              <span style={{ fontSize: '1rem', lineHeight: 1 }}>{t.icon}</span>
              <div className="flex-1 min-w-0">
                <span className="font-medium text-white">{t.title}</span>
                <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>
                  {t.body}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
