import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'

export type AIProvider = 'auto' | 'cloudflare' | 'anthropic' | 'google' | 'openai' | 'groq' | 'deepseek' | 'xai' | 'mistral' | 'cohere' | 'together' | 'perplexity' | 'azure' | 'bedrock' | 'ollama'

export const AI_PROVIDER_META: Record<AIProvider, { label: string; model: string; color: string; paid: boolean; keyEnv: string }> = {
  auto:        { label: 'Auto',       model: 'Auto-detect',         color: '#8b5cf6',  paid: false, keyEnv: '' },
  cloudflare:  { label: 'Cloudflare', model: '@cf/meta/llama-3.1-8b-instruct-fp8', color: '#f38020', paid: false, keyEnv: '' },
  anthropic:   { label: 'Claude',     model: 'claude-sonnet-4-6',   color: '#d97706',  paid: true,  keyEnv: 'ANTHROPIC_API_KEY' },
  google:      { label: 'Gemini',     model: 'gemini-2.0-flash',    color: '#4285F4',  paid: true,  keyEnv: 'GOOGLE_API_KEY' },
  openai:      { label: 'OpenAI',     model: 'gpt-4o',              color: '#10a37f',  paid: true,  keyEnv: 'OPENAI_API_KEY' },
  groq:        { label: 'Groq',       model: 'llama-3.3-70b-versatile', color: '#f97316', paid: true, keyEnv: 'GROQ_API_KEY' },
  deepseek:    { label: 'DeepSeek',   model: 'deepseek-chat',       color: '#4f46e5',  paid: true,  keyEnv: 'DEEPSEEK_API_KEY' },
  xai:         { label: 'xAI Grok',   model: 'grok-2-1212',         color: '#000000',  paid: true,  keyEnv: 'XAI_API_KEY' },
  mistral:     { label: 'Mistral',    model: 'mistral-large-latest', color: '#7c3aed', paid: true,  keyEnv: 'MISTRAL_API_KEY' },
  cohere:      { label: 'Cohere',     model: 'command-r-plus',      color: '#39594D',  paid: true,  keyEnv: 'COHERE_API_KEY' },
  together:    { label: 'Together',   model: 'Mixtral-8x7B',        color: '#0d9488',  paid: true,  keyEnv: 'TOGETHER_API_KEY' },
  perplexity:  { label: 'Perplexity', model: 'sonar-pro',           color: '#2563eb',  paid: true,  keyEnv: 'PERPLEXITY_API_KEY' },
  azure:       { label: 'Azure OpenAI', model: 'gpt-4o',            color: '#0078D4',  paid: true,  keyEnv: 'AZURE_OPENAI_API_KEY' },
  bedrock:     { label: 'AWS Bedrock', model: 'claude-3-sonnet',    color: '#FF9900',  paid: true,  keyEnv: 'BEDROCK_REGION' },
  ollama:      { label: 'Ollama',     model: 'llama3.2',            color: '#6366f1',  paid: false, keyEnv: 'OLLAMA_BASE_URL' },
}

export const ALL_PROVIDERS: AIProvider[] = Object.keys(AI_PROVIDER_META).filter(p => p !== 'auto') as AIProvider[]

const STORAGE_KEY = 'cost_detective_ai_provider'

type AIProviderContextValue = {
  provider: AIProvider
  setProvider: (p: AIProvider) => void
  providersHealth: Record<string, { available: boolean; model: string }>
  setProvidersHealth: (h: Record<string, { available: boolean; model: string }>) => void
}

const AIProviderContext = createContext<AIProviderContextValue>({
  provider: 'auto',
  setProvider: () => {},
  providersHealth: {},
  setProvidersHealth: () => {},
})

export function AIProviderProvider({ children }: { children: ReactNode }) {
  const [provider, setProviderState] = useState<AIProvider>(() => {
    try {
      const v = localStorage.getItem(STORAGE_KEY)
      if (v && v in AI_PROVIDER_META) return v as AIProvider
    } catch {}
    return 'auto'
  })
  const [providersHealth, setProvidersHealth] = useState<Record<string, { available: boolean; model: string }>>({})

  const setProvider = (p: AIProvider) => {
    setProviderState(p)
    try { localStorage.setItem(STORAGE_KEY, p) } catch {}
  }

  return (
    <AIProviderContext.Provider value={{ provider, setProvider, providersHealth, setProvidersHealth }}>
      {children}
    </AIProviderContext.Provider>
  )
}

export function useAIProvider() {
  return useContext(AIProviderContext)
}
