import { useState, useRef } from 'react'
import { agent, type AgentAnalysisRequest } from '../api'
import { useNavigate } from 'react-router-dom'
import { Code, GitBranch, Upload, File, X, CheckCircle, ArrowRight, Copy, ExternalLink } from 'lucide-react'

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

type InputMode = 'paste' | 'repo' | 'upload'

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

function ResultPanel({ result }: { result: any }) {
  const [copiedFix, setCopiedFix] = useState<number | null>(null)
  if (!result) return null
  const issues = result.issues || []
  const resources = result.resources || []
  const suggestions = result.suggestions || []
  const connections = result.connections || []
  const [expandedIssue, setExpandedIssue] = useState<number | null>(null)

  const copyFix = (text: string, idx: number) => {
    navigator.clipboard.writeText(text)
    setCopiedFix(idx)
    setTimeout(() => setCopiedFix(null), 2000)
  }

  if (result.explanation) {
    return (
      <div className="app-card p-4">
        <h3 className="font-semibold mb-3">Explanation</h3>
        <div className="text-sm whitespace-pre-wrap leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
          {result.explanation}
        </div>
      </div>
    )
  }

  if (issues.length > 0 || resources.length > 0) {
    return (
      <div className="space-y-4">
        {/* Summary cards */}
        <div className="grid grid-cols-3 gap-2">
          <div className="app-card p-3 text-center">
            <p className="text-2xl font-bold" style={{ color: '#6366f1' }}>{resources.length}</p>
            <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>Resources</p>
          </div>
          <div className="app-card p-3 text-center">
            <p className="text-2xl font-bold" style={{ color: issues.length > 0 ? '#f59e0b' : '#10b981' }}>{issues.length}</p>
            <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>Issues</p>
          </div>
          <div className="app-card p-3 text-center">
            <p className="text-2xl font-bold" style={{ color: '#8b5cf6' }}>{connections.length}</p>
            <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>Connections</p>
          </div>
        </div>

        {result.summary && (
          <div className="app-card p-3">
            <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>{result.summary}</p>
          </div>
        )}

        {/* Issues */}
        {issues.length > 0 && (
          <div className="app-card p-4">
            <h3 className="font-semibold mb-3 flex items-center gap-2">
              <span className="w-5 h-5 rounded-full bg-amber-500/20 flex items-center justify-center text-amber-400 text-xs">{issues.length}</span>
              Issues Found
            </h3>
            <div className="space-y-2">
              {issues.map((issue: any, i: number) => {
                const isExpanded = expandedIssue === i
                const sevColor = issue.severity === 'critical' ? '#ef4444' : issue.severity === 'high' ? '#f97316' : issue.severity === 'medium' ? '#f59e0b' : '#6366f1'
                return (
                  <div key={i} className="rounded-lg overflow-hidden" style={{ border: `1px solid ${sevColor}30` }}>
                    <button onClick={() => setExpandedIssue(isExpanded ? null : i)}
                      className="w-full flex items-center gap-3 p-3 text-left text-sm" style={{ background: `${sevColor}08` }}>
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: sevColor }} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-white">{issue.resource || issue.resource_name || 'Resource'}</span>
                          <span className="text-xs px-1.5 py-0.5 rounded" style={{ color: sevColor, background: `${sevColor}15` }}>{issue.severity}</span>
                        </div>
                        <p className="text-xs mt-0.5 truncate" style={{ color: 'var(--color-text-tertiary)' }}>{issue.message}</p>
                      </div>
                      <ArrowRight size={12} style={{ color: 'var(--color-text-tertiary)', transform: isExpanded ? 'rotate(90deg)' : 'none', transition: 'transform 0.2s' }} />
                    </button>
                    {isExpanded && (
                      <div className="px-3 pb-3 space-y-2 text-xs" style={{ borderTop: '1px solid var(--color-section-border)' }}>
                        {issue.explanation && <p style={{ color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>{issue.explanation}</p>}
                        {issue.fix && (
                          <div className="rounded-lg p-2.5" style={{ background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.2)' }}>
                            <div className="flex items-center justify-between mb-1">
                              <span className="font-medium" style={{ color: '#10b981' }}>Fix Command</span>
                              <button onClick={() => copyFix(issue.fix, i)} className="flex items-center gap-1" style={{ color: '#10b981' }}>
                                {copiedFix === i ? <CheckCircle size={10} /> : <Copy size={10} />}
                                {copiedFix === i ? 'Copied' : 'Copy'}
                              </button>
                            </div>
                            <pre className="font-mono whitespace-pre-wrap" style={{ color: '#10b981' }}>{issue.fix}</pre>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Resources */}
        {resources.length > 0 && (
          <div className="app-card p-4">
            <h3 className="font-semibold mb-3">Resources ({resources.length})</h3>
            <div className="space-y-1.5">
              {resources.map((res: any, i: number) => (
                <div key={i} className="flex items-center justify-between p-2 rounded-lg text-sm" style={{ background: 'var(--color-section-bg)' }}>
                  <span className="text-white">{res.name || res.id}</span>
                  <span className="text-xs px-2 py-0.5 rounded" style={{ color: 'var(--color-text-tertiary)', background: 'var(--color-card-bg)' }}>{res.type || res.category}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Connections */}
        {connections.length > 0 && (
          <div className="app-card p-4">
            <h3 className="font-semibold mb-3">Connections ({connections.length})</h3>
            <div className="space-y-1.5">
              {connections.map((conn: any, i: number) => (
                <div key={i} className="flex items-center gap-2 p-2 rounded-lg text-xs" style={{ background: 'var(--color-section-bg)' }}>
                  <span className="text-white truncate">{conn.source}</span>
                  <ArrowRight size={10} style={{ color: 'var(--color-text-tertiary)' }} />
                  <span className="text-white truncate">{conn.target}</span>
                  {conn.type && <span className="text-xs px-1.5 py-0.5 rounded" style={{ color: '#8b5cf6', background: 'rgba(139,92,246,0.1)' }}>{conn.type}</span>}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Suggestions */}
        {suggestions.length > 0 && (
          <div className="app-card p-4">
            <h3 className="font-semibold mb-3">Suggestions ({suggestions.length})</h3>
            <div className="space-y-2">
              {suggestions.map((sug: any, i: number) => (
                <div key={i} className="p-3 rounded-lg" style={{ background: 'var(--color-section-bg)', border: '1px solid var(--color-section-border)' }}>
                  <p className="text-sm font-medium text-white">{sug.title || sug.message || 'Suggestion'}</p>
                  <p className="text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>{sug.description || sug.impact || ''}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <pre className="text-xs font-mono whitespace-pre-wrap break-all" style={{ color: 'var(--color-text-secondary)' }}>
      {JSON.stringify(result, null, 2)}
    </pre>
  )
}

export default function AIAgent() {
  const navigate = useNavigate()
  const [inputMode, setInputMode] = useState<InputMode>('paste')
  const [action, setAction] = useState<string>('analyze')
  const [fileType, setFileType] = useState<string>('terraform')
  const [content, setContent] = useState('')
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showHealth, setShowHealth] = useState(false)
  const [health, setHealth] = useState<any>(null)

  // Repo state
  const [repoUrl, setRepoUrl] = useState('')
  const [repoFiles, setRepoFiles] = useState<string[]>([])
  const [cloning, setCloning] = useState(false)
  const [cloneStatus, setCloneStatus] = useState('')

  // Upload state
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploadedFiles, setUploadedFiles] = useState<{ name: string; content: string }[]>([])
  const [uploadStatus, setUploadStatus] = useState('')

  const handleSubmit = async () => {
    const codeToSend = inputMode === 'paste' ? content :
                       inputMode === 'repo' ? repoFiles.join('\n---\n') :
                       uploadedFiles.map(f => `# ${f.name}\n${f.content}`).join('\n---\n')
    if (!codeToSend.trim()) return
    setLoading(true); setError(''); setResult(null)
    try {
      const payload: AgentAnalysisRequest = {
        action: action as AgentAnalysisRequest['action'],
        content: codeToSend,
        file_type: fileType as AgentAnalysisRequest['file_type'],
      }
      let res: unknown
      if (action === 'analyze') res = await agent.analyze(payload)
      else if (action === 'validate') res = await agent.validate(payload)
      else res = await agent.explain(payload)
      setResult(res)
    } catch (e: any) { setError(e.message || 'Request failed') }
    finally { setLoading(false) }
  }

  const checkHealth = async () => {
    try { const h = await agent.health(); setHealth(h); setShowHealth(true) }
    catch (e: any) { setHealth({ error: e.message }); setShowHealth(true) }
  }

  const handleCloneRepo = async () => {
    if (!repoUrl.trim()) return
    setCloning(true); setCloneStatus('Cloning...'); setError('')
    try {
      const res = await fetch(`/api/infra/scan-git?repo_url=${encodeURIComponent(repoUrl)}`)
      const data = await res.json()
      if (data.error) { setError(data.error); setCloneStatus('') }
      else {
        const resources = data.raw_resources || {}
        const lines: string[] = [`# ${repoUrl}`, `# ${Object.keys(resources).length} resources found`, '']
        for (const [id, res] of Object.entries(resources) as [string, any][]) {
          lines.push(`# ${res.name || id} (${res.type})`)
          if (res.config) {
            for (const [k, v] of Object.entries(res.config)) {
              if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') lines.push(`${k} = ${JSON.stringify(v)}`)
            }
          }
          lines.push('')
        }
        setRepoFiles(lines)
        setCloneStatus(`Found ${Object.keys(resources).length} resources`)
      }
    } catch (e: any) { setError(e.message || 'Clone failed'); setCloneStatus('') }
    finally { setCloning(false) }
  }

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return
    setUploadStatus(`Reading ${files.length} file(s)...`)
    const newFiles: { name: string; content: string }[] = []
    let read = 0
    for (const file of Array.from(files)) {
      const reader = new FileReader()
      reader.onload = (ev) => {
        newFiles.push({ name: file.name, content: ev.target?.result as string })
        read++
        if (read === files.length) { setUploadedFiles(prev => [...prev, ...newFiles]); setUploadStatus(`Uploaded ${newFiles.length} file(s)`) }
      }
      reader.readAsText(file)
    }
  }

  const hasCode = inputMode === 'paste' ? content.trim() : inputMode === 'repo' ? repoFiles.length > 0 : uploadedFiles.length > 0

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">AI Agent</h1>
          <p className="app-muted text-sm mt-1">Powered by Cloudflare Workers AI</p>
        </div>
        <button onClick={checkHealth} className="btn-ghost text-sm flex items-center gap-2 px-3 py-1.5 rounded-lg">
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: health?.services?.ai ? '#22c55e' : '#ef4444' }} />
          Health
        </button>
      </div>

      {showHealth && health && (
        <div className="app-card p-3 mb-4 flex items-center gap-6 text-xs">
          <span>Status: <span className={health.status === 'healthy' ? 'text-green-500' : 'text-red-500'}>{health.status || 'unknown'}</span></span>
          <span>AI: <span className={health.services?.ai ? 'text-green-500' : 'text-red-500'}>{health.services?.ai ? 'Available' : 'Down'}</span></span>
          <span>Model: <span className="text-gray-300">{health.model || 'llama-3.2-3b'}</span></span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Input panel (2 cols) */}
        <div className="lg:col-span-2 space-y-4">
          {/* Input Mode */}
          <div className="app-card p-3">
            <div className="grid grid-cols-3 gap-1.5 p-0.5 rounded-lg" style={{ background: 'var(--color-section-bg)' }}>
              {([
                { id: 'paste' as const, icon: <Code size={13} />, label: 'Paste' },
                { id: 'repo' as const, icon: <GitBranch size={13} />, label: 'Repo' },
                { id: 'upload' as const, icon: <Upload size={13} />, label: 'Upload' },
              ]).map(m => (
                <button key={m.id} onClick={() => setInputMode(m.id)}
                  className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all"
                  style={{ background: inputMode === m.id ? '#6366f120' : 'transparent', color: inputMode === m.id ? '#6366f1' : 'var(--color-text-secondary)' }}>
                  {m.icon} {m.label}
                </button>
              ))}
            </div>
          </div>

          {/* Action + File Type */}
          <div className="app-card p-3 space-y-3">
            <div className="grid grid-cols-3 gap-1.5">
              {ACTIONS.map(a => (
                <button key={a.value} onClick={() => setAction(a.value)}
                  className="px-2 py-2 rounded-lg text-xs font-medium transition-all text-center"
                  style={{ background: action === a.value ? '#6366f120' : 'var(--color-section-bg)', border: `1px solid ${action === a.value ? '#6366f1' : 'var(--color-section-border)'}`, color: action === a.value ? '#6366f1' : 'var(--color-text-secondary)' }}>
                  <div>{a.label}</div>
                </button>
              ))}
            </div>
            <div className="grid grid-cols-4 gap-1.5">
              {FILE_TYPES.map(ft => (
                <button key={ft.value} onClick={() => setFileType(ft.value)}
                  className="px-2 py-1.5 rounded text-xs transition-all"
                  style={{ background: fileType === ft.value ? '#6366f120' : 'transparent', border: `1px solid ${fileType === ft.value ? '#6366f1' : 'var(--color-section-border)'}`, color: fileType === ft.value ? '#6366f1' : 'var(--color-text-secondary)' }}>
                  {ft.label}
                </button>
              ))}
            </div>
          </div>

          {/* Input Area */}
          {inputMode === 'paste' && (
            <div className="app-card p-3">
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs font-medium">Code</label>
                <button onClick={() => setContent(SAMPLE_CODE[fileType] || '')} className="text-xs" style={{ color: '#6366f1' }}>Sample</button>
              </div>
              <textarea value={content} onChange={e => setContent(e.target.value)}
                className="app-input w-full h-[280px] font-mono text-xs p-2"
                placeholder={`Paste ${fileType} code...`} spellCheck={false} />
            </div>
          )}

          {inputMode === 'repo' && (
            <div className="app-card p-3 space-y-2">
              <label className="text-xs font-medium">Git Repository</label>
              <input value={repoUrl} onChange={e => setRepoUrl(e.target.value)}
                className="app-input w-full text-xs p-2" placeholder="https://github.com/org/repo.git" />
              <button onClick={handleCloneRepo} disabled={cloning || !repoUrl.trim()}
                className="w-full py-2 rounded-lg text-xs font-medium text-white" style={{ background: '#2563eb' }}>
                {cloning ? 'Cloning...' : 'Clone & Scan'}
              </button>
              {cloneStatus && <p className="text-xs" style={{ color: '#10b981' }}>{cloneStatus}</p>}
            </div>
          )}

          {inputMode === 'upload' && (
            <div className="app-card p-3 space-y-2">
              <label className="text-xs font-medium">Upload Files</label>
              <div onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors"
                style={{ borderColor: 'var(--color-section-border)' }}>
                <Upload size={24} className="mx-auto mb-2" style={{ color: 'var(--color-text-tertiary)' }} />
                <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>Click to browse files</p>
              </div>
              <input ref={fileInputRef} type="file" multiple accept=".tf,.yaml,.yml,.json,.template"
                onChange={handleFileUpload} className="hidden" />
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

          <button onClick={handleSubmit} disabled={loading || !hasCode}
            className="w-full py-3 rounded-xl font-semibold text-white transition-all disabled:opacity-50"
            style={{ background: loading ? '#1e40af' : 'linear-gradient(135deg, #2563eb, #3b82f6)' }}>
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Analyzing...
              </span>
            ) : `Run ${ACTIONS.find(a => a.value === action)?.label}`}
          </button>
        </div>

        {/* Results panel (3 cols) */}
        <div className="lg:col-span-3 app-card p-4 overflow-auto max-h-[calc(100vh-140px)]">
          <h2 className="font-semibold mb-4">Results</h2>
          {error && (
            <div className="rounded-lg p-3 text-sm" style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444' }}>{error}</div>
          )}
          {!result && !error && (
            <div className="text-center py-16" style={{ color: 'var(--color-text-tertiary)' }}>
              <p className="text-4xl mb-3">&#129302;</p>
              <p className="text-sm">Paste code, clone a repo, or upload files</p>
              <p className="text-xs mt-1 opacity-60">Powered by Cloudflare Workers AI</p>
            </div>
          )}
          {result && <ResultPanel result={result} />}
        </div>
      </div>
    </div>
  )
}
