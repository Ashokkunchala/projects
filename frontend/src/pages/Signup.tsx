import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { auth } from '../api'
import { useAuth } from '../AuthContext'
import { AlertCircle, Github, Linkedin } from 'lucide-react'
import LinkedInBadge from '../components/LinkedInBadge'

export default function Signup() {
  const { login }  = useAuth()
  const navigate   = useNavigate()
  const [searchParams]          = useSearchParams()
  const [email, setEmail]       = useState(searchParams.get('email') ?? '')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm]   = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (password !== confirm) { setError('Passwords do not match'); return }
    if (password.length < 8)  { setError('Password must be at least 8 characters'); return }
    setLoading(true)
    try {
      const { user } = await auth.signup(email, password)
      login(user)
      navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Signup failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4" style={{ position: 'relative' }}>

      {/* Grid overlay */}
      <div style={{
        position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0,
        backgroundImage: `linear-gradient(var(--color-section-border) 1px, transparent 1px),
                          linear-gradient(90deg, var(--color-section-border) 1px, transparent 1px)`,
        backgroundSize: '52px 52px',
        opacity: 0.6,
      }} />

      {/* Ambient glow */}
      <div style={{ position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0, overflow: 'hidden' }}>
        <div style={{
          position: 'absolute', width: '600px', height: '600px', borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(99,102,241,0.1) 0%, transparent 65%)',
          top: '-200px', left: '50%', transform: 'translateX(-50%)',
        }} />
      </div>

      <div className="w-full max-w-sm" style={{ position: 'relative', zIndex: 1, animation: 'fadeUp 0.5s ease both' }}>

        {/* Branding */}
        <div className="text-center mb-7">
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '16px' }}>
            <div style={{
              width: '64px', height: '64px', borderRadius: '15px',
              background: 'linear-gradient(135deg, #1a3a6e 0%, #2a5298 100%)',
              border: '1px solid rgba(102,162,234,0.3)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 0 0 7px rgba(99,102,241,0.07), 0 8px 24px rgba(42,82,152,0.38)',
            }}>
              <span style={{ color: '#fff', fontWeight: 900, fontSize: '1.3rem', letterSpacing: '1px', fontFamily: 'Arial, sans-serif' }}>AI</span>
            </div>
          </div>
          <h1 style={{ color: 'var(--color-auth-heading)', fontWeight: 800, fontSize: '1.25rem', letterSpacing: '-0.01em', marginBottom: '5px' }}>
            Cloud Cost Detective
          </h1>
          <p style={{ color: 'var(--color-auth-subtext)', fontSize: '0.82rem' }}>
            Create your account
          </p>
        </div>

        {/* Card */}
        <div style={{
          background: 'var(--color-auth-card-bg)',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          border: '1px solid var(--color-auth-card-border)',
          borderRadius: '18px',
          padding: '32px 28px',
          boxShadow: 'var(--color-auth-card-shadow)',
        }}>
          {error && (
            <div style={{
              display: 'flex', alignItems: 'flex-start', gap: '8px',
              background: 'rgba(254,226,226,0.9)',
              border: '1px solid rgba(252,165,165,0.7)',
              borderRadius: '10px', padding: '10px 14px',
              color: '#b91c1c', fontSize: '0.85rem', marginBottom: '16px',
            }}>
              <AlertCircle size={15} style={{ flexShrink: 0, marginTop: '2px' }} />
              {error}
            </div>
          )}

          {/* Social Login Buttons */}
          <div className="space-y-3 mb-4">
            <button
              onClick={() => window.location.href = `${window.location.origin}/api/auth/github`}
              className="w-full flex items-center justify-center gap-3 py-2.5 rounded-lg border transition-all hover:bg-gray-100 dark:hover:bg-gray-800"
              style={{ borderColor: 'var(--color-section-border)', background: 'var(--color-card-bg)' }}
            >
              <Github size={18} />
              <span className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>Sign up with GitHub</span>
            </button>

            <button
              onClick={() => window.location.href = `${window.location.origin}/api/auth/linkedin`}
              className="w-full flex items-center justify-center gap-3 py-2.5 rounded-lg border transition-all hover:bg-blue-50 dark:hover:bg-blue-900/20"
              style={{ borderColor: '#0A66C2', background: '#0A66C2' }}
            >
              <Linkedin size={18} style={{ color: '#fff' }} />
              <span className="text-sm font-medium text-white">Sign up with LinkedIn</span>
            </button>

            <button
              onClick={() => window.location.href = `${window.location.origin}/api/auth/google`}
              className="w-full flex items-center justify-center gap-3 py-2.5 rounded-lg border transition-all hover:bg-gray-100 dark:hover:bg-gray-800"
              style={{ borderColor: 'var(--color-section-border)', background: 'var(--color-card-bg)' }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
              <span className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>Sign up with Google</span>
            </button>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', margin: '16px 0' }}>
            <div style={{ flex: 1, height: '1px', background: 'var(--color-section-border)' }} />
            <span style={{ color: 'var(--color-text-tertiary)', fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.1em' }}>or</span>
            <div style={{ flex: 1, height: '1px', background: 'var(--color-section-border)' }} />
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {[
              { label: 'Email',            type: 'email',    ph: 'you@company.com', val: email,    set: setEmail,    ac: 'email' },
              { label: 'Password',         type: 'password', ph: 'Min 8 characters', val: password, set: setPassword, ac: 'new-password' },
              { label: 'Confirm Password', type: 'password', ph: 'Repeat password',  val: confirm,  set: setConfirm,  ac: 'new-password' },
            ].map(({ label, type, ph, val, set, ac }) => (
              <div key={label}>
                <label style={{
                  display: 'block',
                  color: 'var(--color-text-secondary)',
                  fontSize: '0.73rem', fontWeight: 600,
                  letterSpacing: '0.06em', textTransform: 'uppercase',
                  marginBottom: '6px',
                }}>{label}</label>
                <input
                  type={type}
                  className="input"
                  placeholder={ph}
                  value={val}
                  onChange={(e) => set(e.target.value)}
                  required
                  autoComplete={ac}
                />
              </div>
            ))}

            <button type="submit" disabled={loading} className="btn-primary w-full py-3 mt-1"
              style={{ background: loading ? undefined : 'linear-gradient(135deg, #1a3a6e 0%, #2a5298 100%)' }}>
              {loading ? 'Creating account…' : 'Create Account'}
            </button>
          </form>

          <div style={{ height: '1px', background: 'var(--color-section-border)', margin: '20px 0' }} />

          <p style={{ textAlign: 'center', color: 'var(--color-text-tertiary)', fontSize: '0.85rem' }}>
            Already have an account?{' '}
            <Link to="/login" style={{ color: 'var(--color-auth-link)', fontWeight: 600, textDecoration: 'none' }}>
              Sign in
            </Link>
          </p>
        </div>

        <div className="flex justify-center mt-6">
          <LinkedInBadge />
        </div>
      </div>
    </div>
  )
}
