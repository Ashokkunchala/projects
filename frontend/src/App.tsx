import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './AuthContext'
import { ThemeProvider } from './ThemeContext'
import Navbar from './components/Navbar'
import Analyze from './pages/Analyze'
import ChangePassword from './pages/ChangePassword'
import CostReports from './pages/CostReports'
import Dashboard from './pages/Dashboard'
import Estimate from './pages/Estimate'
import FreeTier from './pages/FreeTier'
import History from './pages/History'
import InfraVisualizer from './pages/InfraVisualizer'
import Login from './pages/Login'
import Report from './pages/Report'
import Signup from './pages/Signup'
import AIAgent from './pages/AIAgent'
import ChatWidget from './components/ChatWidget'
import type { ReactNode } from 'react'

function LoadingScreen() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
    </div>
  )
}

function Private({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <LoadingScreen />
  return user ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  const { user, loading } = useAuth()

  if (loading) return <LoadingScreen />

  return (
    <ThemeProvider>
      <div className="min-h-screen flex flex-col">
        {user && <Navbar />}
        <main className="flex-1">
          <Routes>
            <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
            <Route path="/signup" element={user ? <Navigate to="/" replace /> : <Signup />} />
            <Route path="/" element={<Private><Dashboard /></Private>} />
            <Route path="/estimate" element={<Private><Estimate /></Private>} />
            <Route path="/cost-reports" element={<Private><CostReports /></Private>} />
            <Route path="/free-tier" element={<Private><FreeTier /></Private>} />
            <Route path="/infra-visualizer" element={<Private><InfraVisualizer /></Private>} />
            <Route path="/ai-agent" element={<Navigate to="/infra-visualizer" replace />} />
            <Route path="/analyze/:id" element={<Private><Analyze /></Private>} />
            <Route path="/report/:id" element={<Private><Report /></Private>} />
            <Route path="/history" element={<Private><History /></Private>} />
            <Route path="/change-password" element={<Private><ChangePassword /></Private>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        {user && <ChatWidget />}
      </div>
    </ThemeProvider>
  )
}
