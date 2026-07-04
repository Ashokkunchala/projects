import { useState, useRef, useEffect, useCallback } from 'react'
import { MessageCircle, X, Send, Trash2, History, Loader2, Bot, User } from 'lucide-react'
import { useChat, ChatProvider } from './ChatContext'
import { agent } from '../api'
import ChatMarkdown from './ChatMarkdown'

function ChatWidgetInner() {
  const { messages, loading, error, sendMessage, clearMessages, loadConversation } = useChat()
  const [input, setInput] = useState('')
  const [open, setOpen] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [conversations, setConversations] = useState<Array<{ id: number; title: string; updated_at: string }>>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  useEffect(() => {
    if (showHistory) {
      agent.conversations.list().then(res => setConversations(res.conversations || [])).catch(() => {})
    }
  }, [showHistory])

  const handleSend = useCallback(async () => {
    if (!input.trim() || loading) return
    const msg = input.trim()
    setInput('')
    await sendMessage(msg)
  }, [input, loading, sendMessage])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const quickActions = [
    { label: 'Analyze my scan', msg: 'Analyze my latest scan results and tell me the top 3 things I should fix first.' },
    { label: 'Suggest fixes', msg: 'What are the highest priority fixes I should apply to reduce my cloud costs?' },
    { label: 'Explain costs', msg: 'Help me understand where my cloud spending is going and how to optimize it.' },
  ]

  const handleQuickAction = (msg: string) => {
    sendMessage(msg)
  }

  return (
    <>
      {/* Toggle Button */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-blue-600 hover:bg-blue-700 text-white shadow-lg flex items-center justify-center transition-all hover:scale-105"
          title="AI Assistant"
        >
          <MessageCircle size={24} />
        </button>
      )}

      {/* Chat Panel */}
      {open && (
        <div className="fixed bottom-6 right-6 z-50 w-[420px] h-[600px] max-h-[80vh] bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700 flex flex-col overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 bg-blue-600 text-white">
            <div className="flex items-center gap-2">
              <Bot size={20} />
              <div>
                <div className="font-semibold text-sm">AI Cost Detective</div>
                <div className="text-xs opacity-80">Powered by Llama 3.1 8B</div>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setShowHistory(!showHistory)}
                className="p-1.5 hover:bg-white/20 rounded-lg transition-colors"
                title="Conversation history"
              >
                <History size={16} />
              </button>
              <button
                onClick={clearMessages}
                className="p-1.5 hover:bg-white/20 rounded-lg transition-colors"
                title="New conversation"
              >
                <Trash2 size={16} />
              </button>
              <button
                onClick={() => setOpen(false)}
                className="p-1.5 hover:bg-white/20 rounded-lg transition-colors"
              >
                <X size={16} />
              </button>
            </div>
          </div>

          {/* History Sidebar */}
          {showHistory && (
            <div className="border-b border-gray-200 dark:border-gray-700 max-h-40 overflow-y-auto">
              {conversations.length === 0 ? (
                <div className="p-3 text-xs text-gray-500 dark:text-gray-400 text-center">No conversations yet</div>
              ) : (
                conversations.map(conv => (
                  <button
                    key={conv.id}
                    onClick={() => { loadConversation(conv.id); setShowHistory(false) }}
                    className="w-full text-left px-4 py-2 hover:bg-gray-50 dark:hover:bg-gray-800 text-xs border-b border-gray-100 dark:border-gray-800 transition-colors"
                  >
                    <div className="font-medium text-gray-800 dark:text-gray-200 truncate">{conv.title}</div>
                    <div className="text-gray-400 dark:text-gray-500 mt-0.5">{new Date(conv.updated_at).toLocaleDateString()}</div>
                  </button>
                ))
              )}
            </div>
          )}

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 && !loading && (
              <div className="text-center py-8">
                <Bot size={40} className="mx-auto mb-3 text-blue-500 opacity-50" />
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                  Ask me anything about your cloud infrastructure, costs, or optimization.
                </p>
                <div className="space-y-2">
                  {quickActions.map((action, i) => (
                    <button
                      key={i}
                      onClick={() => handleQuickAction(action.msg)}
                      className="block w-full text-left px-3 py-2 text-xs bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-750 rounded-lg text-gray-600 dark:text-gray-300 transition-colors border border-gray-200 dark:border-gray-700"
                    >
                      {action.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i} className={`flex gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                {msg.role === 'assistant' && (
                  <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center flex-shrink-0 mt-1">
                    <Bot size={14} className="text-white" />
                  </div>
                )}
                <div className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200'
                }`}>
                  {msg.role === 'assistant' ? (
                    <ChatMarkdown content={msg.content} />
                  ) : (
                    <span className="whitespace-pre-wrap">{msg.content}</span>
                  )}
                </div>
                {msg.role === 'user' && (
                  <div className="w-7 h-7 rounded-full bg-gray-400 flex items-center justify-center flex-shrink-0 mt-1">
                    <User size={14} className="text-white" />
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="flex gap-2">
                <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center flex-shrink-0">
                  <Bot size={14} className="text-white" />
                </div>
                <div className="bg-gray-100 dark:bg-gray-800 rounded-xl px-3 py-2 flex items-center gap-2">
                  <Loader2 size={14} className="animate-spin text-blue-500" />
                  <span className="text-xs text-gray-500">Thinking...</span>
                </div>
              </div>
            )}

            {error && (
              <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 text-xs text-red-600 dark:text-red-400">
                {error}
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="p-3 border-t border-gray-200 dark:border-gray-700">
            <div className="flex items-end gap-2">
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about your cloud costs..."
                className="flex-1 resize-none rounded-xl bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 max-h-24"
                rows={1}
                disabled={loading}
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || loading}
                className="w-9 h-9 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white flex items-center justify-center transition-colors flex-shrink-0"
              >
                <Send size={16} />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default function ChatWidget() {
  return (
    <ChatProvider>
      <ChatWidgetInner />
    </ChatProvider>
  )
}
