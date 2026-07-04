import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import { useTheme } from '../ThemeContext'
import { BarChart3, History, KeyRound, LogOut, Sun, Moon, Calculator, TrendingDown, Cloud, GitBranch } from 'lucide-react'

export default function Navbar() {
  const { user, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const navigate  = useNavigate()
  const location  = useLocation()

  const handleLogout = () => { logout(); navigate('/login') }
  const isActive = (path: string) => location.pathname === path

  const navItems = [
    { to: '/',              Icon: BarChart3,    label: 'Dashboard' },
    { to: '/estimate',      Icon: Calculator,   label: 'Estimator' },
    { to: '/cost-reports',  Icon: TrendingDown,  label: 'Reports' },
    { to: '/free-tier',     Icon: Cloud,         label: 'Free Tier' },
    { to: '/infra-visualizer', Icon: GitBranch,  label: 'Infra & AI' },
    { to: '/history',       Icon: History,       label: 'History' },
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
