import { useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft, AlertTriangle, RefreshCw, Folder, GitBranch, Code,
  X, Search, ZoomIn, ZoomOut, Maximize2, ChevronDown, ChevronRight,
  MessageCircle, ArrowRight, Server, Database, HardDrive, Network,
  Shield, Cloud, Brain, BarChart3, Copy, CheckCircle, Upload, File,
  Play, Loader2, Wifi, WifiOff
} from 'lucide-react'
import { agent, infraViz, type AgentAnalysisRequest } from '../api'
import ArchDiagram from '../components/ArchDiagram'

// ─── Types ────────────────────────────────────────────────────────────────

interface InfraNode {
  id: string; label: string; type: string; category: string; color: string
  x: number; y: number; width: number; height: number
  config: Record<string, unknown>; estimated_cost: number; free_tier_eligible: boolean
}

interface InfraEdge { source: string; target: string; type: string; valid?: boolean; description?: string }

interface Suggestion {
  type: string; severity: string; resource: string; resource_id: string
  message: string; explanation: string; fix?: string; fix_example?: string; estimated_savings?: string
}

interface BrokenConnection { source: string; source_name: string; reference: string; message: string }

interface InfraResult {
  nodes: InfraNode[]; edges: InfraEdge[]; broken_connections: BrokenConnection[]; suggestions: Suggestion[]
  summary: { total_resources: number; total_edges: number; broken_connections: number; suggestions: number; high_severity: number; estimated_monthly_cost: number; free_tier_eligible: number; categories: Record<string, number> }
}

interface AgentResult {
  issues: any[]; resources: any[]; connections: any[]; suggestions: any[]
  summary?: string; explanation?: string
}

interface PreApplyResult {
  nodes: InfraNode[]; edges: InfraEdge[]; suggestions: Suggestion[]
  summary: { total_resources: number; total_edges: number; broken_connections: number; suggestions: number; high_severity: number; estimated_monthly_cost: number; free_tier_eligible: number; categories: Record<string, number> }
  architecture_summary: string; resource_count_by_type: Record<string, number>
}

// ─── Constants ────────────────────────────────────────────────────────────

const CAT: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
  compute: { icon: <Server size={14} />, color: '#6366f1', label: 'Compute' },
  storage: { icon: <HardDrive size={14} />, color: '#8b5cf6', label: 'Storage' },
  database: { icon: <Database size={14} />, color: '#06b6d4', label: 'Database' },
  networking: { icon: <Network size={14} />, color: '#10b981', label: 'Networking' },
  security: { icon: <Shield size={14} />, color: '#ef4444', label: 'Security' },
  load_balancer: { icon: <BarChart3 size={14} />, color: '#f59e0b', label: 'Load Balancer' },
  container: { icon: <Cloud size={14} />, color: '#3b82f6', label: 'Container' },
  serverless: { icon: <Brain size={14} />, color: '#ec4899', label: 'Serverless' },
  dns: { icon: <Globe size={14} />, color: '#14b8a6', label: 'DNS' },
  cache: { icon: <Database size={14} />, color: '#f97316', label: 'Cache' },
  queue: { icon: <Cloud size={14} />, color: '#a855f7', label: 'Queue' },
  monitoring: { icon: <BarChart3 size={14} />, color: '#64748b', label: 'Monitoring' },
}

const FILE_TYPES = [
  { value: 'terraform', label: 'Terraform' },
  { value: 'cloudformation', label: 'CloudFormation' },
  { value: 'kubernetes', label: 'Kubernetes' },
  { value: 'docker-compose', label: 'Docker Compose' },
] as const

const ACTIONS = [
  { value: 'analyze', label: 'Analyze', desc: 'Resources, cost & security' },
  { value: 'validate', label: 'Validate', desc: 'Security & compliance' },
  { value: 'explain', label: 'Explain', desc: 'Plain English' },
] as const

const SAMPLE_CODE: Record<string, string> = {
  terraform: `resource "aws_instance" "web" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t2.micro"
  tags = { Name = "web-server" }
}

resource "aws_s3_bucket" "data" {
  bucket = "my-data-bucket"
}

resource "aws_rds_instance" "db" {
  engine         = "mysql"
  instance_class = "db.t3.micro"
  allocated_storage = 20
}`,
  cloudformation: `Resources:
  WebServer:
    Type: AWS::EC2::Instance
    Properties:
      InstanceType: t2.micro
      ImageId: ami-0c55b159cbfafe1f0`,
  kubernetes: `apiVersion: v1
kind: Pod
metadata:
  name: nginx
spec:
  containers:
  - name: nginx
    image: nginx:latest`,
  'docker-compose': `version: '3'
services:
  web:
    image: nginx:latest
    ports:
      - "80:80"`,
}

function Globe({ size }: { size: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" /></svg>
}

const safe = <T,>(arr: T[] | undefined | null): T[] => Array.isArray(arr) ? arr : []

type InputMode = 'paste' | 'repo' | 'upload'

// ─── Main Component ───────────────────────────────────────────────────────

export default function InfraVisualizer() {
  const navigate = useNavigate()

  // Input state
  const [inputMode, setInputMode] = useState<InputMode>('paste')
  const [code, setCode] = useState('')
  const [fileType, setFileType] = useState<string>('terraform')
  const [gitUrl, setGitUrl] = useState('')
  const [repoFiles, setRepoFiles] = useState<string[]>([])
  const [cloning, setCloning] = useState(false)
  const [cloneStatus, setCloneStatus] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploadedFiles, setUploadedFiles] = useState<{ name: string; content: string }[]>([])

  // Action state
  const [action, setAction] = useState<string>('analyze')

  // Data state
  const [infraData, setInfraData] = useState<InfraResult | null>(null)
  const [agentResult, setAgentResult] = useState<AgentResult | null>(null)
  const [preApplyResult, setPreApplyResult] = useState<PreApplyResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [health, setHealth] = useState<any>(null)
  const [showHealth, setShowHealth] = useState(false)

  // Canvas state
  const canvasRef = useRef<HTMLDivElement>(null)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [isPanning, setIsPanning] = useState(false)
  const panStart = useRef({ x: 0, y: 0, px: 0, py: 0 })
  const [selectedNode, setSelectedNode] = useState<InfraNode | null>(null)
  const [draggingNode, setDraggingNode] = useState<string | null>(null)
  const dragOffset = useRef({ x: 0, y: 0 })
  const [searchQuery, setSearchQuery] = useState('')
  const [showFlow, setShowFlow] = useState(true)
  const [showSuggestions, setShowSuggestions] = useState(true)
  const [expandedSuggestion, setExpandedSuggestion] = useState<number | null>(null)
  const [copiedFix, setCopiedFix] = useState<number | null>(null)
  const [expandedIssue, setExpandedIssue] = useState<number | null>(null)

  // ─── Data Loading ─────────────────────────────────────────────────────

  const handleFetchInfra = useCallback(async (fetcher: () => Promise<unknown>) => {
    setLoading(true); setError(''); setAgentResult(null)
    try {
      const result = await fetcher() as InfraResult
      setInfraData({
        nodes: safe(result?.nodes), edges: safe(result?.edges),
        broken_connections: safe(result?.broken_connections),
        suggestions: safe(result?.suggestions),
        summary: result?.summary || { total_resources: 0, total_edges: 0, broken_connections: 0, suggestions: 0, high_severity: 0, estimated_monthly_cost: 0, free_tier_eligible: 0, categories: {} },
      })
    } catch (err) { setError(err instanceof Error ? err.message : 'Failed') }
    finally { setLoading(false) }
  }, [])

  const handleRunAgent = useCallback(async () => {
    const codeToSend = inputMode === 'paste' ? code :
                       inputMode === 'repo' ? repoFiles.join('\n---\n') :
                       inputMode === 'upload' ? uploadedFiles.map(f => `# ${f.name}\n${f.content}`).join('\n---\n') : code
    if (!codeToSend.trim()) return
    setLoading(true); setError(''); setInfraData(null)
    try {
      const payload: AgentAnalysisRequest = {
        action: action as AgentAnalysisRequest['action'],
        content: codeToSend,
        file_type: fileType as AgentAnalysisRequest['file_type'],
      }
      let res: any
      if (action === 'analyze') res = await agent.analyze(payload)
      else if (action === 'validate') res = await agent.validate(payload)
      else res = await agent.explain(payload)

      setAgentResult({
        issues: res?.issues || [],
        resources: res?.resources || [],
        connections: res?.connections || [],
        suggestions: res?.suggestions || [],
        summary: res?.summary,
        explanation: res?.explanation,
      })

      // Convert agent result to infra nodes for visualization
      if (res?.resources?.length > 0 || res?.issues?.length > 0) {
        const nodes: InfraNode[] = []
        const edges: InfraEdge[] = []

        // Create nodes from resources
        ;(res.resources || []).forEach((r: any, i: number) => {
          const cat = guessCategory(r.type || r.name || '')
          nodes.push({
            id: r.id || r.name || `resource-${i}`,
            label: r.name || r.id || 'Unknown',
            type: r.type || r.category || 'unknown',
            category: cat,
            color: CAT[cat]?.color || '#64748b',
            x: (i % 4) * 200 + 50, y: Math.floor(i / 4) * 120 + 50,
            width: 160, height: 80,
            config: r.config || {},
            estimated_cost: r.estimated_cost || 0,
            free_tier_eligible: r.free_tier_eligible || false,
          })
        })

        // Create nodes from issues if no resources
        if (nodes.length === 0) {
          const seen = new Set<string>()
          ;(res.issues || []).forEach((issue: any, i: number) => {
            const rid = issue.resource_id || issue.resource || `issue-${i}`
            if (seen.has(rid)) return
            seen.add(rid)
            const cat = guessCategory(issue.service || '')
            nodes.push({
              id: rid, label: issue.resource_name || rid, type: issue.service || 'unknown',
              category: cat, color: CAT[cat]?.color || '#64748b',
              x: (nodes.length % 4) * 200 + 50, y: Math.floor(nodes.length / 4) * 120 + 50,
              width: 160, height: 80, config: {}, estimated_cost: issue.potential_monthly_savings || 0,
              free_tier_eligible: false,
            })
          })
        }

        // Create edges from connections
        ;(res.connections || []).forEach((c: any) => {
          if (c.source && c.target) {
            edges.push({ source: c.source, target: c.target, type: c.type || 'connects_to', valid: true })
          }
        })

        // Auto-generate edges from issues if none exist
        if (edges.length === 0 && nodes.length > 1) {
          for (let i = 1; i < nodes.length; i++) {
            edges.push({ source: nodes[0].id, target: nodes[i].id, type: 'connects_to', valid: true })
          }
        }

        setInfraData({
          nodes, edges,
          broken_connections: [],
          suggestions: (res.suggestions || []).map((s: any) => ({
            type: s.type || 'info', severity: s.severity || 'medium',
            resource: s.resource || '', resource_id: s.resource_id || '',
            message: s.message || s.title || '', explanation: s.description || s.explanation || '',
            fix: s.fix || s.implementation || '', fix_example: s.fix_example || '',
            estimated_savings: s.impact || '',
          })),
          summary: {
            total_resources: nodes.length, total_edges: edges.length,
            broken_connections: 0, suggestions: (res.suggestions || []).length,
            high_severity: (res.suggestions || []).filter((s: any) => s.severity === 'high').length,
            estimated_monthly_cost: nodes.reduce((s, n) => s + (n.estimated_cost || 0), 0),
            free_tier_eligible: nodes.filter(n => n.free_tier_eligible).length,
            categories: nodes.reduce((acc, n) => { acc[n.category] = (acc[n.category] || 0) + 1; return acc }, {} as Record<string, number>),
          },
        })
      }
    } catch (e: any) { setError(e.message || 'Request failed') }
    finally { setLoading(false) }
  }, [inputMode, code, repoFiles, uploadedFiles, action, fileType])

  const handleCloneRepo = async () => {
    if (!gitUrl.trim()) return
    setCloning(true); setCloneStatus('Cloning...'); setError('')
    try {
      const res = await fetch(`/api/infra/scan-git?repo_url=${encodeURIComponent(gitUrl)}`)
      const data = await res.json()
      if (data.error) { setError(data.error); setCloneStatus('') }
      else {
        const resources = data.raw_resources || {}
        const lines: string[] = [`# ${gitUrl}`, `# ${Object.keys(resources).length} resources`, '']
        for (const [id, res] of Object.entries(resources) as [string, any][]) {
          lines.push(`# ${res.name || id} (${res.type})`)
          if (res.config) for (const [k, v] of Object.entries(res.config)) if (typeof v === 'string' || typeof v === 'number') lines.push(`${k} = ${JSON.stringify(v)}`)
          lines.push('')
        }
        setRepoFiles(lines); setCloneStatus(`Found ${Object.keys(resources).length} resources`)
      }
    } catch (e: any) { setError(e.message || 'Clone failed'); setCloneStatus('') }
    finally { setCloning(false) }
  }

  const handlePreApply = useCallback(async () => {
    const codeToSend = inputMode === 'paste' ? code :
                       inputMode === 'repo' ? repoFiles.join('\n') :
                       inputMode === 'upload' ? uploadedFiles.map(f => f.content).join('\n') : code
    if (!codeToSend.trim()) return
    setLoading(true); setError(''); setAgentResult(null)
    try {
      const result = await infraViz.preApply(codeToSend, fileType) as PreApplyResult
      setPreApplyResult(result)
      setInfraData({
        nodes: safe(result?.nodes), edges: safe(result?.edges),
        broken_connections: [],
        suggestions: safe(result?.suggestions),
        summary: result?.summary || { total_resources: 0, total_edges: 0, broken_connections: 0, suggestions: 0, high_severity: 0, estimated_monthly_cost: 0, free_tier_eligible: 0, categories: {} },
      })
    } catch (e: any) { setError(e.message || 'Pre-apply analysis failed') }
    finally { setLoading(false) }
  }, [inputMode, code, repoFiles, uploadedFiles, fileType])

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files; if (!files || files.length === 0) return
    const newFiles: { name: string; content: string }[] = []; let read = 0
    for (const file of Array.from(files)) {
      const reader = new FileReader()
      reader.onload = (ev) => { newFiles.push({ name: file.name, content: ev.target?.result as string }); read++; if (read === files.length) setUploadedFiles(prev => [...prev, ...newFiles]) }
      reader.readAsText(file)
    }
  }

  const checkHealth = async () => {
    try { const h = await agent.health(); setHealth(h); setShowHealth(true) }
    catch (e: any) { setHealth({ error: e.message }); setShowHealth(true) }
  }

  // ─── Canvas Handlers ──────────────────────────────────────────────────

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault(); setZoom(z => Math.min(3, Math.max(0.2, z + (e.deltaY > 0 ? -0.1 : 0.1))))
  }, [])

  const handleCanvasMouseDown = useCallback((e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('.infra-node')) return
    setIsPanning(true); panStart.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y }
  }, [pan])

  const handleCanvasMouseMove = useCallback((e: React.MouseEvent) => {
    if (isPanning) setPan({ x: panStart.current.px + (e.clientX - panStart.current.x), y: panStart.current.py + (e.clientY - panStart.current.y) })
    if (draggingNode && infraData) {
      const rect = canvasRef.current?.getBoundingClientRect(); if (!rect) return
      const node = infraData.nodes.find(n => n.id === draggingNode)
      if (node) { node.x = (e.clientX - rect.left - pan.x) / zoom - dragOffset.current.x; node.y = (e.clientY - rect.top - pan.y) / zoom - dragOffset.current.y; setInfraData({ ...infraData }) }
    }
  }, [isPanning, draggingNode, infraData, pan, zoom])

  const handleNodeMouseDown = useCallback((e: React.MouseEvent, node: InfraNode) => {
    e.stopPropagation(); const rect = canvasRef.current?.getBoundingClientRect(); if (!rect) return
    dragOffset.current = { x: (e.clientX - rect.left - pan.x) / zoom - node.x, y: (e.clientY - rect.top - pan.y) / zoom - node.y }
    setDraggingNode(node.id); setSelectedNode(node)
  }, [pan, zoom])

  const layoutNodes = useCallback(() => {
    if (!infraData || infraData.nodes.length === 0) return
    const cols = Math.ceil(Math.sqrt(infraData.nodes.length))
    infraData.nodes.forEach((node, i) => { node.x = (i % cols) * 200 + 50; node.y = Math.floor(i / cols) * 120 + 50 })
    setInfraData({ ...infraData })
  }, [infraData])

  // ─── Helpers ──────────────────────────────────────────────────────────

  const guessCategory = (type: string): string => {
    const t = type.toLowerCase()
    if (/ec2|instance|compute|lambda|ecs|eks/.test(t)) return 'compute'
    if (/s3|ebs|volume|storage|efs/.test(t)) return 'storage'
    if (/rds|dynamodb|database|elasticache|redis/.test(t)) return 'database'
    if (/vpc|subnet|network|elb|alb|load|nat|gateway/.test(t)) return 'networking'
    if (/security|iam|kms|waf/.test(t)) return 'security'
    if (/cloudwatch|monitoring|logs/.test(t)) return 'monitoring'
    return 'compute'
  }

  const copyFix = (text: string, idx: number) => { navigator.clipboard.writeText(text); setCopiedFix(idx); setTimeout(() => setCopiedFix(null), 2000) }

  const hasData = infraData && infraData.nodes.length > 0
  const hasCode = inputMode === 'paste' ? code.trim() : inputMode === 'repo' ? repoFiles.length > 0 : uploadedFiles.length > 0

  const filteredNodes = (infraData?.nodes || []).filter(n => !searchQuery || n.label.toLowerCase().includes(searchQuery.toLowerCase()) || n.type.toLowerCase().includes(searchQuery.toLowerCase()))
  const brokenIds = new Set(safe(infraData?.broken_connections).map(b => b.source))

  // ─── Render ───────────────────────────────────────────────────────────

  return (
    <div className="h-[calc(100vh-64px)] flex flex-col">
      {/* Top bar */}
      <div className="flex items-center gap-2 px-3 py-2 border-b shrink-0" style={{ borderColor: 'var(--color-section-border)', background: 'var(--color-card-bg)' }}>
        <button onClick={() => navigate(-1)} className="btn-ghost p-1.5"><ArrowLeft size={16} /></button>
        <span className="text-sm font-semibold text-white">Infrastructure & AI Agent</span>

        {/* Input mode tabs */}
        <div className="flex gap-1 ml-3 p-0.5 rounded-lg" style={{ background: 'var(--color-section-bg)' }}>
          {([
            { id: 'paste' as const, icon: <Code size={11} />, label: 'Paste Code' },
            { id: 'repo' as const, icon: <GitBranch size={11} />, label: 'Clone Repo' },
            { id: 'upload' as const, icon: <Upload size={11} />, label: 'Upload' },
          ]).map(m => (
            <button key={m.id} onClick={() => { setInputMode(m.id); setInfraData(null); setAgentResult(null); setPreApplyResult(null) }}
              className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-all"
              style={{ background: inputMode === m.id ? '#6366f120' : 'transparent', color: inputMode === m.id ? '#6366f1' : 'var(--color-text-secondary)' }}>
              {m.icon}{m.label}
            </button>
          ))}
        </div>

        {/* Action selector */}
        {inputMode !== 'paste' && (
          <div className="flex gap-1 ml-2 p-0.5 rounded-lg" style={{ background: 'var(--color-section-bg)' }}>
            {ACTIONS.map(a => (
              <button key={a.value} onClick={() => setAction(a.value)}
                className="px-2 py-1 rounded text-xs font-medium transition-all"
                style={{ background: action === a.value ? '#10b98120' : 'transparent', color: action === a.value ? '#10b981' : 'var(--color-text-secondary)' }}>
                {a.label}
              </button>
            ))}
            <button onClick={handlePreApply} disabled={loading || !(code.trim() || repoFiles.length > 0 || uploadedFiles.length > 0)}
              className="px-2 py-1 rounded text-xs font-medium transition-all"
              style={{ background: 'rgba(139,92,246,0.15)', color: '#8b5cf6' }}>
              Pre-Apply
            </button>
          </div>
        )}

        {/* Input fields */}
        {inputMode === 'repo' && (
          <div className="flex items-center gap-2 flex-1 ml-3">
            <input value={gitUrl} onChange={e => setGitUrl(e.target.value)} placeholder="https://github.com/user/repo.git" className="input text-xs font-mono flex-1" />
            <button onClick={handleCloneRepo} disabled={cloning || !gitUrl.trim()} className="btn-primary text-xs px-3 py-1 flex items-center gap-1">
              {cloning ? <Loader2 size={11} className="animate-spin" /> : <GitBranch size={11} />} {cloning ? 'Cloning...' : 'Clone'}
            </button>
          </div>
        )}

        {cloneStatus && <span className="text-xs ml-2" style={{ color: '#10b981' }}>{cloneStatus}</span>}

        {/* Controls */}
        {hasData && (
          <div className="flex items-center gap-1 ml-auto">
            <button onClick={layoutNodes} className="btn-ghost p-1 text-xs" title="Auto-layout">Layout</button>
            <button onClick={() => setShowFlow(!showFlow)} className="btn-ghost p-1 text-xs" style={{ color: showFlow ? '#10b981' : undefined }}>
              {showFlow ? 'Flow On' : 'Flow Off'}
            </button>
            <button onClick={() => setZoom(z => Math.max(0.2, z - 0.15))} className="btn-ghost p-1"><ZoomOut size={13} /></button>
            <span className="text-xs w-9 text-center" style={{ color: 'var(--color-text-tertiary)' }}>{Math.round(zoom * 100)}%</span>
            <button onClick={() => setZoom(z => Math.min(3, z + 0.15))} className="btn-ghost p-1"><ZoomIn size={13} /></button>
            <button onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }) }} className="btn-ghost p-1"><Maximize2 size={13} /></button>
          </div>
        )}

        <button onClick={checkHealth} className="btn-ghost p-1 flex items-center gap-1 text-xs">
          {health?.services?.ai ? <Wifi size={12} style={{ color: '#10b981' }} /> : <WifiOff size={12} style={{ color: '#ef4444' }} />}
        </button>
      </div>

      {error && <div className="flex items-center gap-2 px-3 py-1.5 text-red-400 text-xs shrink-0" style={{ background: 'rgba(239,68,68,0.1)' }}><AlertTriangle size={12} /> {error}</div>}

      {showHealth && health && (
        <div className="flex items-center gap-6 px-3 py-1.5 text-xs shrink-0" style={{ background: 'var(--color-section-bg)' }}>
          <span>Worker: <span className={health.status === 'healthy' ? 'text-green-500' : 'text-red-500'}>{health.status || 'unknown'}</span></span>
          <span>AI: <span className={health.services?.ai ? 'text-green-500' : 'text-red-500'}>{health.services?.ai ? 'Available' : 'Down'}</span></span>
          <span>Model: <span className="text-gray-300">{health.model || 'llama-3.2-3b'}</span></span>
          <button onClick={() => setShowHealth(false)} className="ml-auto" style={{ color: 'var(--color-text-tertiary)' }}><X size={12} /></button>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left panel — input */}
        <div className="w-72 border-r flex flex-col shrink-0" style={{ borderColor: 'var(--color-section-border)', background: 'var(--color-card-bg)' }}>
          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            {/* Paste mode */}
            {inputMode === 'paste' && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium">Infrastructure Code</label>
                  <button onClick={() => setCode(SAMPLE_CODE[fileType] || '')} className="text-xs" style={{ color: '#6366f1' }}>Sample</button>
                </div>
                <select value={fileType} onChange={e => setFileType(e.target.value)} className="input text-xs w-full">
                  {FILE_TYPES.map(ft => <option key={ft.value} value={ft.value}>{ft.label}</option>)}
                </select>
                <textarea value={code} onChange={e => setCode(e.target.value)}
                  className="input w-full font-mono text-xs p-2" style={{ height: '300px', resize: 'none' }}
                  placeholder={`Paste ${fileType} code...`} spellCheck={false} />
              </div>
            )}

            {/* Upload mode */}
            {inputMode === 'upload' && (
              <div className="space-y-2">
                <label className="text-xs font-medium">Upload Files</label>
                <div onClick={() => fileInputRef.current?.click()}
                  className="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors"
                  style={{ borderColor: 'var(--color-section-border)' }}>
                  <Upload size={24} className="mx-auto mb-2" style={{ color: 'var(--color-text-tertiary)' }} />
                  <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>Click to browse files</p>
                </div>
                <input ref={fileInputRef} type="file" multiple accept=".tf,.yaml,.yml,.json,.template" onChange={handleFileUpload} className="hidden" />
                {uploadedFiles.length > 0 && (
                  <div className="space-y-1">
                    {uploadedFiles.map((f, i) => (
                      <div key={i} className="flex items-center justify-between p-1.5 rounded text-xs" style={{ background: 'var(--color-section-bg)' }}>
                        <span className="flex items-center gap-1.5"><File size={10} style={{ color: '#6366f1' }} />{f.name}</span>
                        <button onClick={() => setUploadedFiles(prev => prev.filter((_, j) => j !== i))} style={{ color: '#ef4444' }}><X size={10} /></button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Run button */}
        {inputMode !== 'paste' && (
              <button onClick={handleRunAgent} disabled={loading || !hasCode}
                className="w-full py-2.5 rounded-lg text-sm font-semibold text-white transition-all disabled:opacity-50"
                style={{ background: loading ? '#1e40af' : 'linear-gradient(135deg, #2563eb, #3b82f6)' }}>
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <Loader2 size={14} className="animate-spin" /> Analyzing...
                  </span>
                ) : (
                  <span className="flex items-center justify-center gap-2">
                    <Play size={14} /> Run {ACTIONS.find(a => a.value === action)?.label}
                  </span>
                )}
              </button>
            )}

            {/* Agent results summary */}
            {agentResult && (
              <div className="space-y-2">
                <h4 className="text-xs font-medium" style={{ color: 'var(--color-text-tertiary)' }}>Results</h4>
                {agentResult.summary && <p className="text-xs p-2 rounded" style={{ background: 'var(--color-section-bg)', color: 'var(--color-text-secondary)' }}>{agentResult.summary}</p>}
                {agentResult.explanation && <p className="text-xs p-2 rounded whitespace-pre-wrap" style={{ background: 'var(--color-section-bg)', color: 'var(--color-text-secondary)' }}>{agentResult.explanation}</p>}

                {/* Issues list */}
                {(agentResult.issues || []).length > 0 && (
                  <div className="space-y-1">
                    <p className="text-xs font-medium" style={{ color: '#f59e0b' }}>Issues ({agentResult.issues.length})</p>
                    {agentResult.issues.map((issue: any, i: number) => (
                      <div key={i} className="p-2 rounded text-xs" style={{ background: 'var(--color-section-bg)', borderLeft: `3px solid ${issue.severity === 'high' ? '#ef4444' : issue.severity === 'medium' ? '#f59e0b' : '#6366f1'}` }}>
                        <p className="font-medium text-white">{issue.resource || issue.resource_name || 'Resource'}</p>
                        <p style={{ color: 'var(--color-text-tertiary)' }}>{issue.message}</p>
                        {issue.fix && (
                          <button onClick={() => copyFix(issue.fix, i)} className="mt-1 flex items-center gap-1" style={{ color: '#10b981' }}>
                            {copiedFix === i ? <CheckCircle size={10} /> : <Copy size={10} />}
                            {copiedFix === i ? 'Copied' : 'Copy fix'}
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* Resources list */}
                {(agentResult.resources || []).length > 0 && (
                  <div className="space-y-1">
                    <p className="text-xs font-medium" style={{ color: '#6366f1' }}>Resources ({agentResult.resources.length})</p>
                    {agentResult.resources.slice(0, 10).map((r: any, i: number) => (
                      <div key={i} className="flex items-center justify-between p-1.5 rounded text-xs" style={{ background: 'var(--color-section-bg)' }}>
                        <span className="text-white truncate">{r.name || r.id}</span>
                        <span style={{ color: 'var(--color-text-tertiary)', fontSize: '0.6rem' }}>{r.type}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Architecture diagram — shows when there are nodes */}
            {infraData && infraData.nodes.length > 0 && (
              <div className="space-y-3">
                <ArchDiagram
                  resources={Object.fromEntries(infraData.nodes.map(n => [n.id, { type: n.type, name: n.label, config: n.config }]))}
                  edges={infraData.edges}
                  fileType={fileType}
                />
              </div>
            )}

            {/* Pre-Apply summary */}
            {preApplyResult && (
              <div className="space-y-3">
                {preApplyResult.architecture_summary && (
                  <div className="p-2 rounded text-xs whitespace-pre-wrap" style={{ background: 'var(--color-section-bg)', color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>
                    {preApplyResult.architecture_summary}
                  </div>
                )}
                {preApplyResult.summary?.estimated_monthly_cost > 0 && (
                  <div className="p-2 rounded text-xs" style={{ background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.2)' }}>
                    <span style={{ color: '#10b981', fontWeight: 600 }}>Estimated cost: ${preApplyResult.summary.estimated_monthly_cost}/month</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right panel — canvas + details */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {hasData ? (
            <>
              {/* Canvas */}
              <div className="flex-1 relative overflow-hidden" ref={canvasRef}
                onWheel={handleWheel} onMouseDown={handleCanvasMouseDown} onMouseMove={handleCanvasMouseMove}
                onMouseUp={() => { setIsPanning(false); setDraggingNode(null) }} onMouseLeave={() => { setIsPanning(false); setDraggingNode(null) }}
                style={{ background: 'var(--color-section-bg)', cursor: isPanning ? 'grabbing' : draggingNode ? 'move' : 'grab' }}>

                <svg className="absolute inset-0 w-full h-full" style={{ pointerEvents: 'none' }}>
                  <defs>
                    <pattern id="g" width={40 * zoom} height={40 * zoom} patternUnits="userSpaceOnUse" x={pan.x % (40 * zoom)} y={pan.y % (40 * zoom)}>
                      <circle cx={1} cy={1} r={0.5} fill="rgba(100,116,139,0.15)" />
                    </pattern>
                    <marker id="arrow" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="rgba(99,102,241,0.6)" /></marker>
                    <marker id="arrow-red" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#ef4444" /></marker>
                  </defs>
                  <rect width="100%" height="100%" fill="url(#g)" />
                </svg>

                <div className="absolute" style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, transformOrigin: '0 0' }}>
                  {/* Edges */}
                  <svg className="absolute" style={{ width: '5000px', height: '5000px', pointerEvents: 'none', zIndex: 1 }}>
                    {safe(infraData!.edges).map((edge, i) => {
                      const src = infraData!.nodes.find(n => n.id === edge.source)
                      const tgt = infraData!.nodes.find(n => n.id === edge.target)
                      if (!src || !tgt) return null
                      const sc = { x: src.x + src.width / 2, y: src.y + src.height / 2 }
                      const tc = { x: tgt.x + tgt.width / 2, y: tgt.y + tgt.height / 2 }
                      const mx = (sc.x + tc.x) / 2
                      const isBroken = brokenIds.has(edge.source) || brokenIds.has(edge.target)
                      const color = isBroken ? '#ef4444' : 'rgba(99,102,241,0.35)'
                      return (
                        <g key={i}>
                          <path d={`M ${sc.x} ${sc.y} C ${mx} ${sc.y}, ${mx} ${tc.y}, ${tc.x} ${tc.y}`}
                            fill="none" stroke={color} strokeWidth={isBroken ? 2.5 : 2}
                            strokeDasharray={isBroken ? '4,4' : 'none'}
                            markerEnd={showFlow ? `url(${isBroken ? '#arrow-red' : '#arrow'})` : undefined} />
                          {showFlow && edge.type && (
                            <text x={mx} y={(sc.y + tc.y) / 2 - 8} textAnchor="middle"
                              style={{ fontSize: '10px', fill: 'var(--color-text-tertiary)', fontFamily: 'system-ui' }}>{edge.type}</text>
                          )}
                        </g>
                      )
                    })}
                  </svg>

                  {/* Nodes */}
                  {filteredNodes.map(node => {
                    const sel = selectedNode?.id === node.id
                    const cat = CAT[node.category] || { icon: <Cloud size={14} />, color: '#64748b', label: node.category }
                    const hasIssue = brokenIds.has(node.id)
                    const nodeColor = hasIssue ? '#ef4444' : cat.color
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
                            <span style={{ color: cat.color }}>{cat.icon}</span>
                            <span className="text-xs font-semibold text-white truncate">{node.label}</span>
                          </div>
                          <span className="text-xs truncate" style={{ color: 'var(--color-text-tertiary)', fontSize: '0.62rem' }}>{node.type}</span>
                          {node.estimated_cost > 0 && (
                            <span className="text-xs mt-0.5 px-1 rounded inline-block w-fit" style={{ color: '#10b981', background: '#10b98115', fontSize: '0.58rem' }}>${(node.estimated_cost || 0).toFixed(0)}/mo</span>
                          )}
                        </div>
                        <div className="absolute w-2.5 h-2.5 rounded-full" style={{ background: nodeColor, top: -5, left: '50%', transform: 'translateX(-50%)', border: '2px solid var(--color-card-bg)' }} />
                        <div className="absolute w-2.5 h-2.5 rounded-full" style={{ background: nodeColor, bottom: -5, left: '50%', transform: 'translateX(-50%)', border: '2px solid var(--color-card-bg)' }} />
                      </div>
                    )
                  })}
                </div>

                {/* Summary bar */}
                {infraData!.summary && (
                  <div className="absolute bottom-3 left-3 flex gap-1.5" style={{ zIndex: 20 }}>
                    {[
                      { label: 'Resources', value: infraData!.summary.total_resources, color: '#6366f1' },
                      { label: 'Connections', value: infraData!.summary.total_edges, color: '#8b5cf6' },
                      { label: 'Cost', value: `$${infraData!.summary.estimated_monthly_cost}`, color: '#10b981' },
                      ...(infraData!.summary.high_severity > 0 ? [{ label: 'Issues', value: infraData!.summary.high_severity, color: '#f59e0b' }] : []),
                    ].map(s => (
                      <div key={s.label} className="px-2.5 py-1 rounded-lg" style={{ background: 'var(--color-card-bg)', border: '1px solid var(--color-section-border)' }}>
                        <p className="text-xs font-bold" style={{ color: s.color }}>{s.value}</p>
                        <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.55rem' }}>{s.label}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Bottom panel — suggestions + details */}
              {(safe(infraData!.suggestions).length > 0 || selectedNode) && (
                <div className="border-t max-h-[200px] overflow-y-auto" style={{ borderColor: 'var(--color-section-border)', background: 'var(--color-card-bg)' }}>
                  <div className="flex items-center gap-4 p-2">
                    {/* Selected node info */}
                    {selectedNode && (
                      <div className="flex items-center gap-3 text-xs flex-1">
                        <span style={{ color: CAT[selectedNode.category]?.color }}>{CAT[selectedNode.category]?.icon}</span>
                        <span className="font-medium text-white">{selectedNode.label}</span>
                        <span style={{ color: 'var(--color-text-tertiary)' }}>{selectedNode.type}</span>
                        {selectedNode.estimated_cost > 0 && <span style={{ color: '#10b981' }}>${selectedNode.estimated_cost}/mo</span>}
                      </div>
                    )}

                    {/* Suggestions */}
                    {safe(infraData!.suggestions).length > 0 && (
                      <div className="flex-1">
                        <button onClick={() => setShowSuggestions(!showSuggestions)} className="flex items-center gap-1.5 text-xs font-medium" style={{ color: '#f59e0b' }}>
                          <MessageCircle size={12} /> Suggestions ({safe(infraData!.suggestions).length})
                          {showSuggestions ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                        </button>
                        {showSuggestions && (
                          <div className="mt-2 space-y-1.5 max-h-[140px] overflow-y-auto">
                            {safe(infraData!.suggestions).map((sug, i) => (
                              <div key={i} className="p-2 rounded-lg text-xs" style={{
                                background: sug.severity === 'high' ? 'rgba(239,68,68,0.05)' : 'rgba(245,158,11,0.05)',
                                border: `1px solid ${sug.severity === 'high' ? '#ef444440' : '#f59e0b40'}`,
                              }}>
                                <p className="font-medium text-white">{sug.message}</p>
                                {sug.fix && (
                                  <button onClick={() => copyFix(sug.fix!, i)} className="mt-1 flex items-center gap-1" style={{ color: '#10b981' }}>
                                    {copiedFix === i ? <CheckCircle size={10} /> : <Copy size={10} />}
                                    {copiedFix === i ? 'Copied' : 'Copy fix'}
                                  </button>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          ) : (
            /* Empty state */
            <div className="flex-1 flex items-center justify-center">
              {loading ? (
                <div className="text-center" style={{ color: 'var(--color-text-tertiary)' }}>
                  <Loader2 size={32} className="mx-auto mb-3 animate-spin" style={{ color: '#6366f1' }} />
                  <p className="text-sm">Analyzing...</p>
                </div>
              ) : (
                <div className="text-center" style={{ color: 'var(--color-text-tertiary)' }}>
                  <Cloud size={48} className="mx-auto mb-4 opacity-30" />
                  <p className="text-lg font-semibold text-white mb-2">Infrastructure & AI Agent</p>
                  <p className="text-sm mb-1">Visualize infrastructure and analyze IaC code</p>
                  <p className="text-xs opacity-60">Use the left panel to paste code, clone repos, or upload files</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
