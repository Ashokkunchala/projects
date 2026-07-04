import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import { agent } from '../api'
import type { AgentContext, ChatMessage } from '../types'

interface ChatState {
  messages: ChatMessage[]
  loading: boolean
  conversationId: number | null
  error: string | null
  context: AgentContext | null
}

interface ChatContextValue extends ChatState {
  sendMessage: (content: string, context?: AgentContext) => Promise<void>
  clearMessages: () => void
  setContext: (ctx: AgentContext | null) => void
  loadConversation: (id: number) => Promise<void>
}

const ChatCtx = createContext<ChatContextValue | null>(null)

export function ChatProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ChatState>({
    messages: [],
    loading: false,
    conversationId: null,
    error: null,
    context: null,
  })

  const setContext = useCallback((ctx: AgentContext | null) => {
    setState(s => ({ ...s, context: ctx }))
  }, [])

  const clearMessages = useCallback(() => {
    setState(s => ({ ...s, messages: [], conversationId: null, error: null }))
  }, [])

  const sendMessage = useCallback(async (content: string, overrideContext?: AgentContext) => {
    const ctx = overrideContext || state.context
    const userMsg: ChatMessage = { role: 'user', content }

    setState(s => ({ ...s, messages: [...s.messages, userMsg], loading: true, error: null }))

    try {
      const chatMessages: ChatMessage[] = [...state.messages, userMsg]
      const res = await agent.chat({
        messages: chatMessages,
        context: ctx || undefined,
        conversation_id: state.conversationId || undefined,
        max_tokens: 2048,
        temperature: 0.3,
      })

      const assistantMsg: ChatMessage = { role: 'assistant', content: res.response || 'No response received.' }
      setState(s => ({
        ...s,
        messages: [...s.messages, assistantMsg],
        loading: false,
        conversationId: res.conversation_id || s.conversationId,
      }))
    } catch (e: any) {
      setState(s => ({
        ...s,
        loading: false,
        error: e.message || 'Failed to get response',
      }))
    }
  }, [state.messages, state.conversationId, state.context])

  const loadConversation = useCallback(async (id: number) => {
    setState(s => ({ ...s, loading: true, error: null }))
    try {
      const res = await agent.conversations.messages(id)
      const msgs: ChatMessage[] = (res.messages || []).map(m => ({
        role: m.role as 'user' | 'assistant' | 'system',
        content: m.content,
      }))
      setState(s => ({ ...s, messages: msgs, conversationId: id, loading: false }))
    } catch (e: any) {
      setState(s => ({ ...s, loading: false, error: e.message || 'Failed to load conversation' }))
    }
  }, [])

  return (
    <ChatCtx.Provider value={{ ...state, sendMessage, clearMessages, setContext, loadConversation }}>
      {children}
    </ChatCtx.Provider>
  )
}

export function useChat() {
  const ctx = useContext(ChatCtx)
  if (!ctx) throw new Error('useChat must be used within ChatProvider')
  return ctx
}
