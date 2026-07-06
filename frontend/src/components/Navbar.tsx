import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import { useTheme } from '../ThemeContext'
import { useAIProvider, AI_PROVIDER_META, type AIProvider } from '../AIProviderContext'
import { BarChart3, History, KeyRound, LogOut, Sun, Moon, Calculator, TrendingDown, Cloud, GitBranch, Users, Bell, ShoppingCart, Sparkles, CheckCircle, XCircle } from 'lucide-react'

export default function Navbar() {
  const { user, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const { provider: aiProvider, setProvider: setAiProvider } = useAIProvider()
  const navigate  = useNavigate()
  const location  = useLocation()

  const handleLogout = () => { logout(); navigate('/login') }
  const isActive = (path: string) => location.pathname === path

  const AI_OPTIONS: { value: AIProvider; label: string; model: string }[] = [
    { value: 'auto',       label: 'Auto',       model: 'Auto-detect' },
    { value: 'cloudflare', label: 'Cloudflare',  model: 'Llama 3.1 8B' },
    { value: 'anthropic',  label: 'Claude',      model: 'claude-sonnet-4-6' },
    { value: 'google',     label: 'Gemini',      model: 'gemini-2.0-flash' },
    { value: 'openai',     label: 'OpenAI',      model: 'gpt-4o' },
    { value: 'groq',       label: 'Groq',        model: 'Llama 3.3 70B' },
    { value: 'deepseek',   label: 'DeepSeek',    model: 'deepseek-chat' },
    { value: 'xai',        label: 'xAI Grok',    model: 'grok-2-1212' },
    { value: 'mistral',    label: 'Mistral',     model: 'mistral-large' },
    { value: 'cohere',     label: 'Cohere',      model: 'command-r+' },
    { value: 'together',   label: 'Together',    model: 'Mixtral 8x7B' },
    { value: 'perplexity', label: 'Perplexity',  model: 'sonar-pro' },
    { value: 'azure',      label: 'Azure OpenAI', model: 'gpt-4o' },
    { value: 'bedrock',    label: 'AWS Bedrock', model: 'Claude 3' },
    { value: 'ollama',     label: 'Ollama',      model: 'llama3.2' },
  ]

  const aiLabel = AI_OPTIONS.find(o => o.value === aiProvider)?.label || 'Auto'

  const navItems = [
    { to: '/',              Icon: BarChart3,    label: 'Dashboard' },
    { to: '/estimate',      Icon: Calculator,   label: 'Estimator' },
    { to: '/cost-reports',  Icon: TrendingDown,  label: 'Reports' },
    { to: '/free-tier',     Icon: Cloud,         label: 'Free Tier' },
    { to: '/infra-visualizer', Icon: GitBranch,  label: 'Infra & AI' },
    { to: '/history',       Icon: History,       label: 'History' },
    { to: '/teams',         Icon: Users,         label: 'Teams' },
    { to: '/alerts',        Icon: Bell,          label: 'Alerts' },
    { to: '/rightsizing',   Icon: ShoppingCart,  label: 'RI & Plans' },
  ]

  return (
    <nav className="app-banner sticky top-0 z-50" style={{ boxShadow: '0 4px 24px rgba(0,0,0,0.55)' }}>
      <div style={{ position: 'absolute', inset: 0, zIndex: 0, overflow: 'hidden', pointerEvents: 'none' }}>
        <div style={{ position: 'absolute', width: '300px', height: '300px', borderRadius: '50%', background: 'radial-gradient(circle, rgba(42,82,152,0.22) 0%, transparent 70%)', top: '-140px', left: '-50px' }} />
        <div style={{ position: 'absolute', width: '220px', height: '220px', borderRadius: '50%', background: 'radial-gradient(circle, rgba(201,146,42,0.1) 0%, transparent 70%)', top: '-90px', right: '-30px' }} />
      </div>

      <div className="max-w-7xl mx-auto px-3 h-[56px] flex items-center gap-2"
        style={{ position: 'relative', zIndex: 2 }}>

        {/* Logo */}
        <Link to="/" className="flex items-center gap-2 shrink-0 no-underline">
          <div className="app-logo-badge" style={{ width: '32px', height: '32px', fontSize: '0.8rem' }}>AI</div>
          <span className="text-white font-bold text-sm hidden md:block" style={{ letterSpacing: '0.3px' }}>Cost Detective</span>
        </Link>

        {/* Nav links */}
        <div className="flex items-center gap-0.5 ml-2 overflow-x-auto">
          {navItems.map(({ to, Icon, label }) => (
            <Link key={to} to={to}
              className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs font-medium transition-all whitespace-nowrap"
              style={{
                background: isActive(to) ? 'rgba(255,255,255,0.12)' : 'transparent',
                color: isActive(to) ? '#fff' : 'rgba(255,255,255,0.6)',
              }}>
              <Icon size={13} />
              <span>{label}</span>
            </Link>
          ))}
        </div>

        {/* Right controls */}
        <div className="flex items-center gap-1 ml-auto shrink-0">
          {user?.email && (
            <span className="hidden lg:block truncate max-w-[140px] text-xs" style={{ color: 'rgba(255,255,255,0.4)' }}>
              {user.email}
            </span>
          )}

          {/* AI Provider selector - compact dropdown */}
          <div className="relative group" style={{ zIndex: 100 }}>
            <button className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[10px] font-medium transition-all"
              style={{ background: 'rgba(167,139,250,0.12)', color: '#a78bfa', border: '1px solid rgba(167,139,250,0.2)' }}>
              <Sparkles size={10} />
              {AI_PROVIDER_META[aiProvider]?.label || 'Auto'}
              <svg width="8" height="8" viewBox="0 0 24 24" fill="none"><path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
            <div className="absolute right-0 top-full mt-1 w-56 rounded-xl overflow-hidden shadow-2xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-150"
              style={{ background: '#1a1a24', border: '1px solid rgba(255,255,255,0.08)', maxHeight: '320px', overflowY: 'auto' }}>
              {AI_OPTIONS.map(opt => (
                <button key={opt.value} onClick={() => setAiProvider(opt.value)}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-left transition-all hover:bg-white/5"
                  style={{ color: aiProvider === opt.value ? '#a78bfa' : 'rgba(255,255,255,0.6)' }}>
                  {aiProvider === opt.value && <CheckCircle size={10} style={{ color: '#22c55e' }} />}
                  {aiProvider !== opt.value && <div style={{ width: 10 }} />}
                  <span className="font-medium">{opt.label}</span>
                  <span className="ml-auto text-[9px] opacity-40">{opt.model}</span>
                </button>
              ))}
            </div>
          </div>

          <button onClick={toggleTheme} className="p-1.5 rounded-lg transition-colors hover:bg-white/10"
            style={{ color: 'rgba(255,255,255,0.6)' }}
            title={theme === 'dark' ? 'Light mode' : 'Dark mode'}>
            {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
          </button>

          <Link to="/change-password" className="p-1.5 rounded-lg transition-colors hover:bg-white/10"
            style={{ color: isActive('/change-password') ? '#fff' : 'rgba(255,255,255,0.6)' }}>
            <KeyRound size={14} />
          </Link>

          <button onClick={handleLogout} className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs font-medium transition-colors hover:bg-white/10"
            style={{ color: 'rgba(255,255,255,0.6)' }}>
            <LogOut size={13} />
            <span className="hidden sm:block">Logout</span>
          </button>
        </div>
      </div>

      <div className="banner-stripe" />
    </nav>
  )
}
