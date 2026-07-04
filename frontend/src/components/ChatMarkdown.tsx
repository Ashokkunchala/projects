import { useState } from 'react'
import { Copy, Check } from 'lucide-react'

interface ChatMarkdownProps {
  content: string
}

export default function ChatMarkdown({ content }: ChatMarkdownProps) {
  return (
    <div className="prose prose-sm max-w-none dark:prose-invert">
      {parseMarkdown(content)}
    </div>
  )
}

function parseMarkdown(text: string) {
  // Split by code blocks first
  const parts = text.split(/(```[\s\S]*?```)/g)

  return parts.map((part, i) => {
    if (part.startsWith('```')) {
      // Code block
      const lines = part.split('\n')
      const lang = lines[0].replace('```', '').trim()
      const code = lines.slice(1, -1).join('\n') || lines.slice(1).join('\n')
      return <CodeBlock key={i} language={lang} code={code} />
    }
    return <InlineMarkdown key={i} text={part} />
  })
}

function InlineMarkdown({ text }: { text: string }) {
  // Process inline markdown: bold, italic, inline code, links
  const lines = text.split('\n')

  return (
    <>
      {lines.map((line, i) => {
        // Headers
        if (line.startsWith('### ')) return <h4 key={i} className="text-sm font-bold mt-3 mb-1">{renderInline(line.slice(4))}</h4>
        if (line.startsWith('## ')) return <h3 key={i} className="text-base font-bold mt-4 mb-1">{renderInline(line.slice(3))}</h3>
        if (line.startsWith('# ')) return <h2 key={i} className="text-lg font-bold mt-4 mb-1">{renderInline(line.slice(2))}</h2>

        // List items
        if (line.match(/^[-*]\s/)) return <li key={i} className="ml-4">{renderInline(line.slice(2))}</li>
        if (line.match(/^\d+\.\s/)) {
          const num = line.match(/^(\d+)\./)?.[1]
          return <li key={i} className="ml-4 list-decimal">{renderInline(line.replace(/^\d+\.\s/, ''))}</li>
        }

        // Empty line
        if (line.trim() === '') return <br key={i} />

        // Regular paragraph
        return <p key={i} className="my-1">{renderInline(line)}</p>
      })}
    </>
  )
}

function renderInline(text: string) {
  // Process bold, italic, inline code
  const parts: (string | JSX.Element)[] = []
  let remaining = text
  let key = 0

  while (remaining.length > 0) {
    // Inline code
    const codeMatch = remaining.match(/`([^`]+)`/)
    // Bold
    const boldMatch = remaining.match(/\*\*([^*]+)\*\*/)
    // Italic
    const italicMatch = remaining.match(/(?<!\*)\*([^*]+)\*(?!\*)/)
    // Link
    const linkMatch = remaining.match(/\[([^\]]+)\]\(([^)]+)\)/)

    // Find the earliest match
    const matches = [
      codeMatch && { type: 'code', match: codeMatch },
      boldMatch && { type: 'bold', match: boldMatch },
      italicMatch && { type: 'italic', match: italicMatch },
      linkMatch && { type: 'link', match: linkMatch },
    ].filter(Boolean) as Array<{ type: string; match: RegExpMatchArray }>

    if (matches.length === 0) {
      parts.push(remaining)
      break
    }

    // Sort by index
    matches.sort((a, b) => (a.match.index || 0) - (b.match.index || 0))
    const earliest = matches[0]
    const idx = earliest.match.index || 0

    if (idx > 0) parts.push(remaining.slice(0, idx))

    const full = earliest.match[0]
    const inner = earliest.match[1]

    if (earliest.type === 'code') {
      parts.push(<code key={key++} className="bg-gray-200 dark:bg-gray-700 px-1 py-0.5 rounded text-xs font-mono">{inner}</code>)
    } else if (earliest.type === 'bold') {
      parts.push(<strong key={key++} className="font-semibold">{inner}</strong>)
    } else if (earliest.type === 'italic') {
      parts.push(<em key={key++}>{inner}</em>)
    } else if (earliest.type === 'link') {
      parts.push(<a key={key++} href={earliest.match[2]} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline">{inner}</a>)
    }

    remaining = remaining.slice(idx + full.length)
  }

  return parts
}

function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="my-2 rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700">
      <div className="flex items-center justify-between bg-gray-100 dark:bg-gray-800 px-3 py-1 text-xs">
        <span className="text-gray-500 dark:text-gray-400 font-mono">{language || 'code'}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="p-3 overflow-x-auto text-xs font-mono bg-gray-50 dark:bg-gray-900">
        <code>{code}</code>
      </pre>
    </div>
  )
}
