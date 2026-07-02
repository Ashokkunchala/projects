import { useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft, AlertTriangle, CheckCircle, RefreshCw, Folder, GitBranch, Code,
  X, Search, ZoomIn, ZoomOut, Maximize2, ChevronDown, ChevronRight, MessageCircle
} from 'lucide-react'
import { infraViz } from '../api'

interface InfraNode {
  id: string; label: string; type: string; category: string; color: string
  x: number; y: number; width: number; height: number
  config: Record<string, unknown>; estimated_cost: number; free_tier_eligible: boolean
}

interface InfraEdge { source: string; target: string; type: string; valid?: boolean }

interface Suggestion {
  type: string; severity: string; resource: string; resource_id: string
  message: string; explanation: string; fix?: string; fix_example?: string; estimated_savings?: string
}

interface BrokenConnection { source: string; source_name: string; reference: string; message: string }

interface InfraResult {
  nodes: InfraNode[]; edges: InfraEdge[]; broken_connections: BrokenConnection[]; suggestions: Suggestion[]
  summary: { total_resources: number; total_edges: number; broken_connections: number; suggestions: number; high_severity: number; estimated_monthly_cost: number; free_tier_eligible: number; categories: Record<string, number> }
  scanned_files?: { terraform: string[]; cloudformation: string[] }
}

const CAT: Record<string, { icon: string; color: string }> = {
  compute: { icon: '🖥️', color: '#6366f1' }, storage: { icon: '💾', color: '#8b5cf6' },
  database: { icon: '🗄️', color: '#06b6d4' }, networking: { icon: '🌐', color: '#10b981' },
  security: { icon: '🔒', color: '#ef4444' }, load_balancer: { icon: '⚖️', color: '#f59e0b' },
  container: { icon: '📦', color: '#3b82f6' }, serverless: { icon: '⚡', color: '#ec4899' },
  dns: { icon: '🔗', color: '#14b8a6' }, cache: { icon: '⚡', color: '#f97316' },
  queue: { icon: '📨', color: '#a855f7' }, monitoring: { icon: '📊', color: '#64748b' },
}

const safe = <T,>(arr: T[] | undefined | null): T[] => Array.isArray(arr) ? arr : []

export default function InfraVisualizer() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<'project' | 'git' | 'code'>('project')
  const [code, setCode] = useState('')
  const [fileType, setFileType] = useState<'terraform' | 'cloudformation'>('terraform')
  const [directory, setDirectory] = useState('')
  const [gitUrl, setGitUrl] = useState('')
  const [data, setData] = useState<InfraResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const canvasRef = useRef<HTMLDivElement>(null)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [isPanning, setIsPanning] = useState(false)
  const panStart = useRef({ x: 0, y: 0, px: 0, py: 0 })
  const [selectedNode, setSelectedNode] = useState<InfraNode | null>(null)
  const [draggingNode, setDraggingNode] = useState<string | null>(null)
  const dragOffset = useRef({ x: 0, y: 0 })
  const [searchQuery, setSearchQuery] = useState('')
  const [showSuggestions, setShowSuggestions] = useState(true)
  const [expandedSuggestion, setExpandedSuggestion] = useState<number | null>(null)

  const handleFetch = useCallback(async (fetcher: () => Promise<unknown>) => {
    setLoading(true); setError('')
    try {
      const result = await fetcher() as InfraResult
      setData({
        nodes: safe(result?.nodes),
        edges: safe(result?.edges),
        broken_connections: safe(result?.broken_connections),
        suggestions: safe(result?.suggestions),
        summary: result?.summary || { total_resources: 0, total_edges: 0, broken_connections: 0, suggestions: 0, high_severity: 0, estimated_monthly_cost: 0, free_tier_eligible: 0, categories: {} },
        scanned_files: result?.scanned_files,
      })
    } catch (err) { setError(err instanceof Error ? err.message : 'Failed') }
    finally { setLoading(false) }
  }, [])

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    setZoom(z => Math.min(3, Math.max(0.2, z + (e.deltaY > 0 ? -0.1 : 0.1))))
  }, [])

  const handleCanvasMouseDown = useCallback((e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('.infra-node')) return
    setIsPanning(true)
    panStart.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y }
  }, [pan])

  const handleCanvasMouseMove = useCallback((e: React.MouseEvent) => {
    if (isPanning) {
      setPan({ x: panStart.current.px + (e.clientX - panStart.current.x), y: panStart.current.py + (e.clientY - panStart.current.y) })
    }
    if (draggingNode && data) {
      const rect = canvasRef.current?.getBoundingClientRect()
      if (!rect) return
      const node = data.nodes.find(n => n.id === draggingNode)
      if (node) {
        node.x = (e.clientX - rect.left - pan.x) / zoom - dragOffset.current.x
        node.y = (e.clientY - rect.top - pan.y) / zoom - dragOffset.current.y
        setData({ ...data })
      }
    }
  }, [isPanning, draggingNode, data, pan, zoom])

  const handleNodeMouseDown = useCallback((e: React.MouseEvent, node: InfraNode) => {
    e.stopPropagation()
    const rect = canvasRef.current?.getBoundingClientRect()
    if (!rect) return
    dragOffset.current = {
      x: (e.clientX - rect.left - pan.x) / zoom - node.x,
      y: (e.clientY - rect.top - pan.y) / zoom - node.y,
    }
    setDraggingNode(node.id)
    setSelectedNode(node)
  }, [pan, zoom])

  const filteredNodes = data?.nodes.filter(n =>
    !searchQuery || n.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
    n.type.toLowerCase().includes(searchQuery.toLowerCase())
  ) || []

  const brokenIds = new Set(safe(data?.broken_connections).map(b => b.source))

  return (
    <div className="h-[calc(100vh-64px)] flex flex-col">
      {/* Top bar */}
      <div className="flex items-center gap-2 px-3 py-2 border-b shrink-0" style={{ borderColor: 'var(--color-section-border)', background: 'var(--color-card-bg)' }}>
        <button onClick={() => navigate(-1)} className="btn-ghost p-1.5"><ArrowLeft size={16} /></button>
        <span className="text-sm font-semibold text-white">Infrastructure Visualizer</span>

        <div className="flex gap-1 ml-3 p-0.5 rounded-lg" style={{ background: 'var(--color-section-bg)' }}>
          {([
            { id: 'project' as const, icon: <Folder size={11} />, label: 'Project' },
            { id: 'git' as const, icon: <GitBranch size={11} />, label: 'Git' },
            { id: 'code' as const, icon: <Code size={11} />, label: 'Code' },
          ]).map(m => (
            <button key={m.id} onClick={() => setMode(m.id)}
              className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-all"
              style={{ background: mode === m.id ? '#6366f120' : 'transparent', color: mode === m.id ? '#6366f1' : 'var(--color-text-secondary)' }}>
              {m.icon}{m.label}
            </button>
          ))}
        </div>

        {mode === 'project' && (
          <div className="flex items-center gap-2 flex-1 ml-3">
            <input value={directory} onChange={e => setDirectory(e.target.value)} placeholder="/path/to/terraform-project" className="input text-xs font-mono flex-1" />
            <button onClick={() => handleFetch(() => infraViz.scanProject(directory))} disabled={loading || !directory.trim()}
              className="btn-primary text-xs px-3 py-1 flex items-center gap-1">
              {loading ? <RefreshCw size={11} className="animate-spin" /> : <Folder size={11} />} Scan
            </button>
          </div>
        )}
        {mode === 'git' && (
          <div className="flex items-center gap-2 flex-1 ml-3">
            <input value={gitUrl} onChange={e => setGitUrl(e.target.value)} placeholder="https://github.com/user/repo.git" className="input text-xs font-mono flex-1" />
            <button onClick={() => handleFetch(() => infraViz.scanGit(gitUrl))} disabled={loading || !gitUrl.trim()}
              className="btn-primary text-xs px-3 py-1 flex items-center gap-1">
              {loading ? <RefreshCw size={11} className="animate-spin" /> : <GitBranch size={11} />} Scan
            </button>
          </div>
        )}
        {mode === 'code' && (
          <div className="flex items-center gap-2 flex-1 ml-3">
            <select value={fileType} onChange={e => setFileType(e.target.value as typeof fileType)} className="input text-xs" style={{ width: 'auto' }}>
              <option value="terraform">Terraform</option>
              <option value="cloudformation">CloudFormation</option>
            </select>
            <button onClick={() => handleFetch(() => infraViz.parse(code, fileType))} disabled={loading || !code.trim()}
              className="btn-primary text-xs px-3 py-1 flex items-center gap-1">
              {loading ? <RefreshCw size={11} className="animate-spin" /> : <Code size={11} />} Parse
            </button>
          </div>
        )}

        {data && (
          <div className="flex items-center gap-1 ml-auto">
            <button onClick={() => setZoom(z => Math.max(0.2, z - 0.15))} className="btn-ghost p-1"><ZoomOut size={13} /></button>
            <span className="text-xs w-9 text-center" style={{ color: 'var(--color-text-tertiary)' }}>{Math.round(zoom * 100)}%</span>
            <button onClick={() => setZoom(z => Math.min(3, z + 0.15))} className="btn-ghost p-1"><ZoomIn size={13} /></button>
            <button onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }) }} className="btn-ghost p-1"><Maximize2 size={13} /></button>
          </div>
        )}
      </div>

      {error && <div className="flex items-center gap-2 px-3 py-1.5 text-red-400 text-xs shrink-0" style={{ background: 'rgba(239,68,68,0.1)' }}><AlertTriangle size={12} /> {error}</div>}

      {/* Code editor */}
      {mode === 'code' && !data && (
        <div className="flex-1 p-3">
          <textarea value={code} onChange={e => setCode(e.target.value)} className="input w-full font-mono text-xs h-full"
            placeholder={`# Paste Terraform or CloudFormation code...\n\nresource "aws_vpc" "main" {\n  cidr_block = "10.0.0.0/16"\n}\n\nresource "aws_subnet" "public" {\n  vpc_id     = aws_vpc.main.id\n  cidr_block = "10.0.1.0/24"\n}`}
            style={{ resize: 'none', minHeight: '100%' }} />
        </div>
      )}

      {data && (
        <div className="flex-1 flex overflow-hidden">
          {/* Canvas */}
          <div className="flex-1 relative overflow-hidden" ref={canvasRef}
            onWheel={handleWheel} onMouseDown={handleCanvasMouseDown} onMouseMove={handleCanvasMouseMove}
            onMouseUp={() => { setIsPanning(false); setDraggingNode(null) }} onMouseLeave={() => { setIsPanning(false); setDraggingNode(null) }}
            style={{ background: 'var(--color-section-bg)', cursor: isPanning ? 'grabbing' : draggingNode ? 'move' : 'grab' }}>

            {/* Grid */}
            <svg className="absolute inset-0 w-full h-full" style={{ pointerEvents: 'none' }}>
              <defs>
                <pattern id="g" width={40 * zoom} height={40 * zoom} patternUnits="userSpaceOnUse" x={pan.x % (40 * zoom)} y={pan.y % (40 * zoom)}>
                  <circle cx={1} cy={1} r={0.5} fill="rgba(100,116,139,0.15)" />
                </pattern>
              </defs>
              <rect width="100%" height="100%" fill="url(#g)" />
            </svg>

            {/* Transformed content */}
            <div className="absolute" style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, transformOrigin: '0 0' }}>
              {/* Edges */}
              <svg className="absolute" style={{ width: '5000px', height: '5000px', pointerEvents: 'none', zIndex: 1 }}>
                {filteredNodes.length > 0 && safe(data.edges).map((edge, i) => {
                  const src = data.nodes.find(n => n.id === edge.source)
                  const tgt = data.nodes.find(n => n.id === edge.target)
                  if (!src || !tgt) return null
                  const sc = { x: src.x + src.width / 2, y: src.y + src.height / 2 }
                  const tc = { x: tgt.x + tgt.width / 2, y: tgt.y + tgt.height / 2 }
                  const mx = (sc.x + tc.x) / 2
                  const isBroken = brokenIds.has(edge.source) || brokenIds.has(edge.target)
                  return (
                    <g key={i}>
                      <path d={`M ${sc.x} ${sc.y} C ${mx} ${sc.y}, ${mx} ${tc.y}, ${tc.x} ${tc.y}`}
                        fill="none" stroke={isBroken ? '#ef4444' : 'rgba(99,102,241,0.35)'}
                        strokeWidth={isBroken ? 2.5 : 2} strokeDasharray={isBroken ? '4,4' : 'none'} />
                      <circle cx={tc.x} cy={tc.y} r={3} fill={isBroken ? '#ef4444' : 'rgba(99,102,241,0.5)'} />
                    </g>
                  )
                })}
              </svg>

              {/* Nodes */}
              {filteredNodes.map(node => {
                const sel = selectedNode?.id === node.id
                const c = CAT[node.color] || CAT[node.category] || { icon: '📦', color: '#64748b' }
                const hasIssue = brokenIds.has(node.id)
                const nodeColor = hasIssue ? '#ef4444' : node.color
                return (
                  <div key={node.id} className="absolute select-none infra-node"
                    style={{ left: node.x, top: node.y, width: node.width, height: node.height, zIndex: sel ? 10 : 2 }}
                    onMouseDown={(e) => handleNodeMouseDown(e, node)}>
                    <div className="absolute inset-0 rounded-xl" style={{
                      boxShadow: sel ? `0 0 0 2px ${nodeColor}, 0 8px 24px ${nodeColor}40` : hasIssue ? `0 0 0 1.5px #ef4444, 0 4px 12px rgba(239,68,68,0.2)` : '0 2px 8px rgba(0,0,0,0.2)',
                      background: sel ? `${nodeColor}18` : 'var(--color-card-bg)',
                      border: `1.5px solid ${sel ? nodeColor : hasIssue ? '#ef444480' : nodeColor + '50'}`,
                      borderRadius: '12px',
                    }} />
                    <div className="relative p-2 h-full flex flex-col justify-center" style={{ zIndex: 1 }}>
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs">{CAT[node.category]?.icon || '📦'}</span>
                        <span className="text-xs font-semibold text-white truncate">{node.label}</span>
                        {hasIssue && <span className="text-xs">⚠️</span>}
                      </div>
                      <span className="text-xs truncate" style={{ color: 'var(--color-text-tertiary)', fontSize: '0.62rem' }}>{node.type}</span>
                      <div className="flex items-center gap-1 mt-0.5">
                        {node.estimated_cost > 0 && (
                          <span className="text-xs px-1 rounded" style={{ color: '#10b981', background: '#10b98115', fontSize: '0.58rem' }}>${node.estimated_cost.toFixed(0)}/mo</span>
                        )}
                        {node.free_tier_eligible && (
                          <span className="text-xs px-1 rounded" style={{ color: '#f59e0b', background: '#f59e0b15', fontSize: '0.58rem' }}>Free Tier</span>
                        )}
                      </div>
                    </div>
                    {/* Connection dots */}
                    <div className="absolute w-2.5 h-2.5 rounded-full" style={{ background: nodeColor, top: -5, left: '50%', transform: 'translateX(-50%)', border: '2px solid var(--color-card-bg)' }} />
                    <div className="absolute w-2.5 h-2.5 rounded-full" style={{ background: nodeColor, bottom: -5, left: '50%', transform: 'translateX(-50%)', border: '2px solid var(--color-card-bg)' }} />
                  </div>
                )
              })}
            </div>

            {/* Summary bar */}
            {data.summary && (
              <div className="absolute bottom-3 left-3 flex gap-1.5" style={{ zIndex: 20 }}>
                {[
                  { label: 'Resources', value: data.summary.total_resources, color: '#6366f1' },
                  { label: 'Connections', value: data.summary.total_edges, color: '#8b5cf6' },
                  { label: 'Monthly', value: `$${data.summary.estimated_monthly_cost}`, color: '#10b981' },
                  ...(data.summary.broken_connections > 0 ? [{ label: 'Broken', value: data.summary.broken_connections, color: '#ef4444' }] : []),
                  ...(data.summary.high_severity > 0 ? [{ label: 'Issues', value: data.summary.high_severity, color: '#f59e0b' }] : []),
                ].map(s => (
                  <div key={s.label} className="px-2.5 py-1 rounded-lg" style={{ background: 'var(--color-card-bg)', border: '1px solid var(--color-section-border)' }}>
                    <p className="text-xs font-bold" style={{ color: s.color }}>{s.value}</p>
                    <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.55rem' }}>{s.label}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right panel */}
          <div className="w-80 border-l flex flex-col shrink-0" style={{ borderColor: 'var(--color-section-border)', background: 'var(--color-card-bg)' }}>
            {/* Search */}
            <div className="p-2 border-b shrink-0" style={{ borderColor: 'var(--color-section-border)' }}>
              <div className="relative">
                <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: 'var(--color-text-tertiary)' }} />
                <input value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder="Search..." className="input w-full pl-7 text-xs" />
              </div>
            </div>

            <div className="flex-1 overflow-y-auto">
              {/* Suggestions */}
              {safe(data.suggestions).length > 0 && (
                <div className="border-b" style={{ borderColor: 'var(--color-section-border)' }}>
                  <button onClick={() => setShowSuggestions(!showSuggestions)}
                    className="w-full flex items-center justify-between px-3 py-2 text-xs font-medium"
                    style={{ color: data.summary.high_severity > 0 ? '#ef4444' : '#f59e0b' }}>
                    <span className="flex items-center gap-1.5">
                      <MessageCircle size={12} /> Suggestions ({safe(data.suggestions).length})
                    </span>
                    {showSuggestions ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                  </button>
                  {showSuggestions && (
                    <div className="px-2 pb-2 space-y-1.5">
                      {safe(data.suggestions).map((sug, i) => (
                        <div key={i} className="rounded-lg overflow-hidden" style={{
                          border: `1px solid ${sug.severity === 'high' ? '#ef444440' : sug.severity === 'medium' ? '#f59e0b40' : '#6366f130'}`,
                        }}>
                          <button onClick={() => setExpandedSuggestion(expandedSuggestion === i ? null : i)}
                            className="w-full flex items-start gap-2 p-2 text-left text-xs"
                            style={{ background: sug.severity === 'high' ? 'rgba(239,68,68,0.05)' : sug.severity === 'medium' ? 'rgba(245,158,11,0.05)' : 'rgba(99,102,241,0.05)' }}>
                            <span className="shrink-0 mt-0.5">
                              {sug.severity === 'high' ? '🔴' : sug.severity === 'medium' ? '🟡' : '🔵'}
                            </span>
                            <div className="flex-1 min-w-0">
                              <p className="font-medium text-white leading-tight">{sug.message}</p>
                              <p className="mt-0.5" style={{ color: 'var(--color-text-tertiary)', fontSize: '0.6rem' }}>
                                {sug.resource} · {sug.type}
                              </p>
                            </div>
                          </button>
                          {expandedSuggestion === i && (
                            <div className="px-2 pb-2 space-y-2 text-xs" style={{ borderTop: '1px solid var(--color-section-border)', paddingTop: '8px' }}>
                              <p style={{ color: 'var(--color-text-secondary)', lineHeight: 1.5 }}>{sug.explanation}</p>
                              {sug.fix && (
                                <div className="rounded-lg p-2" style={{ background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.2)' }}>
                                  <p className="font-medium" style={{ color: '#10b981', fontSize: '0.65rem' }}>How to fix:</p>
                                  <p style={{ color: 'var(--color-text-secondary)', lineHeight: 1.5 }}>{sug.fix}</p>
                                </div>
                              )}
                              {sug.fix_example && (
                                <pre className="rounded-lg p-2 font-mono" style={{
                                  background: 'var(--color-code-bg)', border: '1px solid var(--color-code-border)',
                                  color: '#10b981', fontSize: '0.65rem', whiteSpace: 'pre-wrap',
                                }}>{sug.fix_example}</pre>
                              )}
                              {sug.estimated_savings && (
                                <p style={{ color: '#10b981', fontSize: '0.65rem' }}>💰 {sug.estimated_savings}</p>
                              )}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Broken connections */}
              {safe(data.broken_connections).length > 0 && (
                <div className="border-b p-2 space-y-1.5" style={{ borderColor: 'var(--color-section-border)', background: 'rgba(239,68,68,0.03)' }}>
                  <p className="text-xs font-medium px-1" style={{ color: '#ef4444' }}>⚠️ Broken References ({safe(data.broken_connections).length})</p>
                  {safe(data.broken_connections).map((bc, i) => (
                    <div key={i} className="p-2 rounded-lg text-xs" style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
                      <p className="text-white font-medium">{bc.source_name}</p>
                      <p style={{ color: 'var(--color-text-secondary)', lineHeight: 1.4, marginTop: '2px' }}>{bc.message}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Resource list */}
              <div className="p-2 space-y-0.5">
                {Object.entries(CAT).map(([cat, meta]) => {
                  const nodes = filteredNodes.filter(n => n.category === cat)
                  if (nodes.length === 0) return null
                  return (
                    <div key={cat}>
                      <p className="text-xs font-medium px-1.5 py-1 flex items-center gap-1" style={{ color: meta.color }}>
                        {meta.icon} {cat.replace(/_/g, ' ')} <span style={{ color: 'var(--color-text-tertiary)' }}>({nodes.length})</span>
                      </p>
                      {nodes.map(node => (
                        <div key={node.id} className="flex items-center gap-2 px-2 py-1 rounded cursor-pointer text-xs transition-all"
                          style={{
                            background: selectedNode?.id === node.id ? `${node.color}15` : 'transparent',
                            borderLeft: selectedNode?.id === node.id ? `2px solid ${node.color}` : '2px solid transparent',
                          }} onClick={() => setSelectedNode(node)}>
                          <span>{meta.icon}</span>
                          <span className="flex-1 truncate text-white">{node.label}</span>
                          {brokenIds.has(node.id) && <span>⚠️</span>}
                          {node.estimated_cost > 0 && <span style={{ color: '#10b981', fontSize: '0.6rem' }}>${node.estimated_cost.toFixed(0)}</span>}
                        </div>
                      ))}
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Node detail panel */}
            {selectedNode && (
              <div className="border-t p-3 space-y-2.5 overflow-y-auto shrink-0" style={{ borderColor: 'var(--color-section-border)', maxHeight: '45%' }}>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-white flex items-center gap-1.5">
                    {CAT[selectedNode.category]?.icon} {selectedNode.label}
                  </span>
                  <button onClick={() => setSelectedNode(null)} className="btn-ghost p-1"><X size={12} /></button>
                </div>
                <div className="grid grid-cols-2 gap-1.5">
                  {[['Type', selectedNode.type], ['Category', selectedNode.category.replace(/_/g, ' ')],
                    ['Cost', `$${selectedNode.estimated_cost.toFixed(2)}/mo`], ['Free Tier', selectedNode.free_tier_eligible ? 'Yes' : 'No'],
                  ].map(([k, v]) => (
                    <div key={k} className="p-1.5 rounded" style={{ background: 'var(--color-section-bg)' }}>
                      <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.55rem' }}>{k}</p>
                      <p className="text-xs font-medium text-white">{v}</p>
                    </div>
                  ))}
                </div>
                <div>
                  <p className="text-xs font-medium mb-1" style={{ color: 'var(--color-text-secondary)' }}>Configuration</p>
                  <pre className="text-xs p-2 rounded-lg overflow-auto" style={{
                    background: 'var(--color-code-bg)', border: '1px solid var(--color-code-border)',
                    maxHeight: '150px', color: 'var(--color-text-secondary)', lineHeight: 1.5,
                  }}>
                    {JSON.stringify(Object.fromEntries(Object.entries(selectedNode.config).filter(([k]) => !k.startsWith('_'))), null, 2)}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Empty states */}
      {!data && !loading && mode !== 'code' && (
        <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--color-text-tertiary)' }}>
          <div className="text-center space-y-2">
            <p className="text-3xl">🏗️</p>
            <p className="text-sm font-medium text-white">Enter a project path or Git URL</p>
            <p className="text-xs">Scans for Terraform/CloudFormation and renders an interactive diagram</p>
          </div>
        </div>
      )}
      {loading && <div className="flex-1 flex items-center justify-center"><RefreshCw size={24} className="animate-spin" style={{ color: '#6366f1' }} /></div>}
    </div>
  )
}
