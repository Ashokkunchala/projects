import { useState } from 'react'
import { Copy, CheckCircle, ChevronDown, ChevronRight, Server, Database, HardDrive, Network, Shield, Cloud } from 'lucide-react'

interface ArchNode {
  id: string; label: string; type: string; category: string
  children?: ArchNode[]; config?: Record<string, unknown>
  estimated_cost?: number; region?: string; vpc?: string
  subnet?: string; is_gateway?: boolean; is_cluster?: boolean
}

interface ArchDiagramProps {
  resources: Record<string, any>
  edges: Array<{ source: string; target: string; type: string }>
  fileType: string
}

const CAT_ICONS: Record<string, React.ReactNode> = {
  compute: <Server size={12} />, storage: <HardDrive size={12} />,
  database: <Database size={12} />, networking: <Network size={12} />,
  security: <Shield size={12} />, container: <Cloud size={12} />,
}

const CAT_COLORS: Record<string, string> = {
  compute: '#6366f1', storage: '#8b5cf6', database: '#06b6d4',
  networking: '#10b981', security: '#ef4444', container: '#3b82f6',
  serverless: '#ec4899', load_balancer: '#f59e0b',
}

function buildHierarchy(resources: Record<string, any>, edges: Array<{ source: string; target: string; type: string }>): ArchNode[] {
  // Group resources by their containment relationships
  const vpcs: Record<string, any[]> = {}
  const orphans: any[] = []

  for (const [id, res] of Object.entries(resources)) {
    const config = res.config || {}
    const vpcId = config.vpc_id || config.VpcId || ''
    const subnetId = config.subnet_id || config.SubnetId || ''

    // Extract VPC reference
    const vpcRef = typeof vpcId === 'string' ? vpcId.match(/([a-z0-9_]+)\.([a-z0-9_]+)\.([a-z0-9_]+)/)?.[2] : null

    if (vpcRef) {
      if (!vpcs[vpcRef]) vpcs[vpcRef] = []
      vpcs[vpcRef].push({ id, ...res, _subnetRef: subnetId ? subnetId.match(/([a-z0-9_]+)\.([a-z0-9_]+)\.([a-z0-9_]+)/)?.[2] : null })
    } else {
      orphans.push({ id, ...res })
    }
  }

  // Build hierarchy
  const result: ArchNode[] = []

  // Add VPCs with their children
  for (const [vpcName, children] of Object.entries(vpcs)) {
    const vpcRes = resources[`aws_vpc.${vpcName}`] || resources[vpcName]
    const subnets: Record<string, ArchNode[]> = {}
    const standalone: ArchNode[] = []

    for (const child of children) {
      const subnetRef = child._subnetRef
      const node: ArchNode = {
        id: child.id,
        label: child.name || child.id.split('.').pop() || 'Unknown',
        type: child.type,
        category: getCategory(child.type),
        config: child.config,
      }

      if (subnetRef) {
        if (!subnets[subnetRef]) subnets[subnetRef] = []
        subnets[subnetRef].push(node)
      } else {
        standalone.push(node)
      }
    }

    // Build subnet groups
    const subnetNodes: ArchNode[] = []
    for (const [subName, subChildren] of Object.entries(subnets)) {
      const subRes = resources[`aws_subnet.${subName}`] || resources[subName]
      subnetNodes.push({
        id: `subnet.${subName}`,
        label: subRes?.name || subName,
        type: 'aws_subnet',
        category: 'networking',
        config: subRes?.config,
        children: subChildren,
      })
    }

    const vpcNode: ArchNode = {
      id: `vpc.${vpcName}`,
      label: vpcRes?.name || vpcName,
      type: 'aws_vpc',
      category: 'networking',
      config: vpcRes?.config,
      children: [...subnetNodes, ...standalone],
    }
    result.push(vpcNode)
  }

  // Add orphan resources (no VPC)
  for (const orphan of orphans) {
    result.push({
      id: orphan.id,
      label: orphan.name || orphan.id.split('.').pop() || 'Unknown',
      type: orphan.type,
      category: getCategory(orphan.type),
      config: orphan.config,
    })
  }

  return result
}

function getCategory(type: string): string {
  const t = type.toLowerCase()
  if (/ec2|instance|compute|lambda|ecs|eks/.test(t)) return 'compute'
  if (/s3|ebs|volume|storage|efs/.test(t)) return 'storage'
  if (/rds|dynamodb|database|elasticache|redis|db_instance/.test(t)) return 'database'
  if (/vpc|subnet|network|elb|alb|load|nat|gateway|igw/.test(t)) return 'networking'
  if (/security|iam|kms|waf/.test(t)) return 'security'
  if (/eks|ecs|kubernetes|container/.test(t)) return 'container'
  return 'compute'
}

function ArchNodeComponent({ node, depth = 0, isLast = false }: { node: ArchNode; depth?: number; isLast?: boolean }) {
  const [expanded, setExpanded] = useState(depth < 2)
  const hasChildren = node.children && node.children.length > 0
  const color = CAT_COLORS[node.category] || '#64748b'
  const icon = CAT_ICONS[node.category] || <Cloud size={12} />

  return (
    <div className="relative">
      {/* Connector line */}
      {depth > 0 && (
        <div className="absolute" style={{
          left: -16, top: 0, width: 16, height: '50%',
          borderBottom: isLast ? 'none' : `2px solid ${color}40`,
          borderRight: `2px solid ${color}40`,
          borderBottomRightRadius: isLast ? '8px' : 0,
        }} />
      )}

      {/* Node card */}
      <div className="flex items-start gap-2 py-1.5">
        {/* Expand/collapse button */}
        {hasChildren ? (
          <button onClick={() => setExpanded(!expanded)}
            className="shrink-0 mt-1 p-0.5 rounded hover:bg-white/10 transition-colors">
            {expanded ? <ChevronDown size={12} style={{ color }} /> : <ChevronRight size={12} style={{ color }} />}
          </button>
        ) : (
          <div className="w-4 shrink-0" />
        )}

        {/* Resource card */}
        <div className="flex-1 rounded-lg p-2.5 transition-all hover:ring-1"
          style={{
            background: `${color}10`,
            border: `1px solid ${color}30`,
            borderLeft: `3px solid ${color}`,
          }}>
          <div className="flex items-center gap-2">
            <span style={{ color }}>{icon}</span>
            <span className="text-xs font-semibold text-white">{node.label}</span>
            <span className="text-xs px-1.5 py-0.5 rounded" style={{ color, background: `${color}20`, fontSize: '0.6rem' }}>
              {node.type.replace('aws_', '')}
            </span>
            {node.estimated_cost && node.estimated_cost > 0 && (
              <span className="text-xs px-1.5 py-0.5 rounded" style={{ color: '#10b981', background: 'rgba(16,185,129,0.1)', fontSize: '0.6rem' }}>
                ${node.estimated_cost}/mo
              </span>
            )}
          </div>

          {/* Config details */}
          {node.config && Object.keys(node.config).length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5">
              {Object.entries(node.config).slice(0, 4).map(([k, v]) => (
                <span key={k} className="text-xs" style={{ color: 'var(--color-text-tertiary)', fontSize: '0.6rem' }}>
                  {k}: <span style={{ color: 'var(--color-text-secondary)' }}>{String(v).substring(0, 30)}</span>
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Children */}
      {hasChildren && expanded && (
        <div className="ml-4 relative" style={{ borderLeft: `2px solid ${color}30` }}>
          {node.children!.map((child, i) => (
            <ArchNodeComponent key={child.id} node={child} depth={depth + 1} isLast={i === node.children!.length - 1} />
          ))}
        </div>
      )}
    </div>
  )
}

export default function ArchDiagram({ resources, edges, fileType }: ArchDiagramProps) {
  const [asciiMode, setAsciiMode] = useState(false)
  const [copied, setCopied] = useState(false)

  const hierarchy = buildHierarchy(resources, edges)

  // Generate ASCII diagram
  const generateAscii = (nodes: ArchNode[], prefix = '', isLast = true): string => {
    let result = ''
    nodes.forEach((node, i) => {
      const connector = isLast && i === nodes.length - 1 ? '└── ' : '├── '
      const childPrefix = isLast && i === nodes.length - 1 ? '    ' : '│   '

      const config = node.config || {}
      const details = []
      if (config.cidr_block) details.push(config.cidr_block)
      if (config.instance_type) details.push(config.instance_type)
      if (config.engine) details.push(config.engine)
      if (config.bucket) details.push(config.bucket)
      const detailStr = details.length > 0 ? ` (${details.join(', ')})` : ''

      result += `${prefix}${connector}${node.label}${detailStr}\n`

      if (node.children && node.children.length > 0) {
        result += generateAscii(node.children, prefix + childPrefix, i === nodes.length - 1)
      }
    })
    return result
  }

  const asciiDiagram = `AWS Account
│
└── ${fileType === 'terraform' ? 'Terraform' : 'CloudFormation'} Resources
${generateAscii(hierarchy, '    ', true)}`

  const copyAscii = () => {
    navigator.clipboard.writeText(asciiDiagram)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">Architecture Diagram</h3>
        <div className="flex gap-1">
          <button onClick={() => setAsciiMode(false)}
            className="px-2 py-1 rounded text-xs font-medium transition-all"
            style={{ background: !asciiMode ? '#6366f120' : 'transparent', color: !asciiMode ? '#6366f1' : 'var(--color-text-secondary)' }}>
            Visual
          </button>
          <button onClick={() => setAsciiMode(true)}
            className="px-2 py-1 rounded text-xs font-medium transition-all"
            style={{ background: asciiMode ? '#6366f120' : 'transparent', color: asciiMode ? '#6366f1' : 'var(--color-text-secondary)' }}>
            ASCII
          </button>
          {asciiMode && (
            <button onClick={copyAscii} className="px-2 py-1 rounded text-xs font-medium transition-all flex items-center gap-1"
              style={{ color: '#10b981' }}>
              {copied ? <CheckCircle size={10} /> : <Copy size={10} />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          )}
        </div>
      </div>

      {asciiMode ? (
        <pre className="p-3 rounded-lg text-xs font-mono overflow-x-auto" style={{
          background: 'var(--color-code-bg)', border: '1px solid var(--color-code-border)',
          color: 'var(--color-text-secondary)', lineHeight: 1.6,
        }}>
          {asciiDiagram}
        </pre>
      ) : (
        <div className="p-3 rounded-lg overflow-auto max-h-[500px]" style={{
          background: 'var(--color-section-bg)', border: '1px solid var(--color-section-border)',
        }}>
          {hierarchy.length > 0 ? (
            <div className="space-y-1">
              <div className="flex items-center gap-2 pb-2 mb-2" style={{ borderBottom: '1px solid var(--color-section-border)' }}>
                <Cloud size={14} style={{ color: '#6366f1' }} />
                <span className="text-xs font-semibold text-white">AWS Account</span>
              </div>
              <div className="ml-2 relative" style={{ borderLeft: '2px solid rgba(99,102,241,0.3)' }}>
                {hierarchy.map((node, i) => (
                  <ArchNodeComponent key={node.id} node={node} depth={0} isLast={i === hierarchy.length - 1} />
                ))}
              </div>
            </div>
          ) : (
            <p className="text-xs text-center py-4" style={{ color: 'var(--color-text-tertiary)' }}>No resources found</p>
          )}
        </div>
      )}
    </div>
  )
}
