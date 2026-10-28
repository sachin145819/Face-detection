import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { LayoutDashboard, ScanSearch, History, LogOut, Menu, X, ChevronsUpDown, Plus, ChevronRight, BookOpen } from 'lucide-react'
import Logo from './Logo.jsx'
import { useAuth } from '../context/AuthContext.jsx'

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/analyze', label: 'New analysis', icon: ScanSearch },
  { to: '/history', label: 'History', icon: History },
]

const CRUMBS = [
  [/^\/dashboard/, 'Dashboard'],
  [/^\/analyze/, 'New analysis'],
  [/^\/history/, 'History'],
  [/^\/analyses\//, 'Analysis report'],
  [/^\/video-analyses\//, 'Video report'],
]

function initials(name = '') {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0].toUpperCase())
    .join('') || 'U'
}

function useEngineStatus() {
  const [status, setStatus] = useState(null)
  useEffect(() => {
    let alive = true
    const load = () =>
      fetch('/api/health')
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then((d) => alive && setStatus(d))
        .catch(() => alive && setStatus({ status: 'down' }))
    load()
    const t = setInterval(load, 30000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])
  return status
}

function EngineStatus() {
  const s = useEngineStatus()
  let dot = 'bg-slate-300'
  let label = 'Checking engine…'
  let detail = ''
  if (s?.status === 'ok') {
    if (s.ml_deep_enabled && s.models_loaded) {
      dot = 'bg-emerald-500'
      label = 'AI engine online'
      detail = 'Forensics + deep models ready'
    } else if (s.ml_deep_enabled) {
      dot = 'bg-amber-400'
      label = 'Loading models'
      detail = 'Forensic checks available'
    } else {
      dot = 'bg-amber-400'
      label = 'Forensics only'
      detail = 'Deep models disabled'
    }
  } else if (s) {
    dot = 'bg-red-500'
    label = 'Engine offline'
    detail = 'Backend not reachable'
  }
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5">
      <div className="flex items-center gap-2 text-xs font-medium text-slate-700">
        <span className="relative flex h-2 w-2">
          {dot === 'bg-emerald-500' ? <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" /> : null}
          <span className={`relative inline-flex h-2 w-2 rounded-full ${dot}`} />
        </span>
        {label}
      </div>
      {detail ? <p className="mt-0.5 pl-4 text-[11px] text-slate-500">{detail}</p> : null}
    </div>
  )
}

function NavItems({ onNavigate }) {
  return (
    <nav className="flex flex-col gap-0.5" aria-label="Main">
      <p className="mb-1 px-3 text-[11px] font-medium uppercase tracking-wider text-slate-400">Workspace</p>
      {NAV.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          onClick={onNavigate}
          className={({ isActive }) =>
            `group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              isActive ? 'bg-slate-100 text-slate-900' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
            }`
          }
        >
          {({ isActive }) => (
            <>
              <Icon className={`h-[18px] w-[18px] ${isActive ? 'text-cyan-600' : 'text-slate-400 group-hover:text-slate-500'}`} aria-hidden />
              {label}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}

function UserMenu() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    const onDoc = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])
  const doLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }
  return (
    <div className="relative" ref={ref}>
      {open ? (
        <div className="absolute bottom-full left-0 right-0 mb-2 animate-fadeIn rounded-lg border border-slate-200 bg-white p-1 shadow-pop" role="menu">
          <div className="border-b border-slate-100 px-3 py-2 text-xs text-slate-500">
            Signed in as
            <div className="truncate text-sm font-medium text-slate-900">{user?.email}</div>
          </div>
          <button onClick={doLogout} className="mt-1 flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-red-600 hover:bg-red-50" role="menuitem">
            <LogOut className="h-4 w-4" aria-hidden /> Sign out
          </button>
        </div>
      ) : null}
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors hover:bg-slate-100"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-900 text-xs font-semibold text-white">
          {initials(user?.name)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-slate-900">{user?.name}</span>
          <span className="block truncate text-xs text-slate-500">{user?.email}</span>
        </span>
        <ChevronsUpDown className="h-4 w-4 text-slate-400" aria-hidden />
      </button>
    </div>
  )
}

function SidebarContent({ onNavigate }) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-16 items-center border-b border-slate-200 px-5">
        <Logo to="/dashboard" dark={false} />
      </div>
      <div className="flex flex-1 flex-col gap-6 overflow-y-auto p-3 pt-5">
        <NavItems onNavigate={onNavigate} />
        <div className="flex flex-col gap-0.5">
          <p className="mb-1 px-3 text-[11px] font-medium uppercase tracking-wider text-slate-400">Resources</p>
          <a href="/docs" target="_blank" rel="noreferrer" className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900">
            <BookOpen className="h-[18px] w-[18px] text-slate-400" aria-hidden /> API reference
          </a>
        </div>
        <div className="mt-auto space-y-3">
          <EngineStatus />
          <div className="border-t border-slate-200 pt-3">
            <UserMenu />
          </div>
        </div>
      </div>
    </div>
  )
}

function TopBar({ onMenu }) {
  const { pathname } = useLocation()
  const crumb = CRUMBS.find(([re]) => re.test(pathname))?.[1] || ''
  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-slate-200 bg-white/85 px-4 backdrop-blur sm:px-6 lg:px-8">
      <button onClick={onMenu} className="-ml-1 rounded-md p-2 text-slate-600 hover:bg-slate-100 lg:hidden" aria-label="Open menu">
        <Menu className="h-5 w-5" />
      </button>
      <div className="lg:hidden">
        <Logo to="/dashboard" dark={false} />
      </div>
      <nav className="hidden items-center gap-1.5 text-sm lg:flex" aria-label="Breadcrumb">
        <Link to="/dashboard" className="text-slate-500 hover:text-slate-900">TruthLens</Link>
        {crumb ? (
          <>
            <ChevronRight className="h-4 w-4 text-slate-300" aria-hidden />
            <span className="font-medium text-slate-900">{crumb}</span>
          </>
        ) : null}
      </nav>
      <div className="ml-auto flex items-center gap-2">
        {pathname !== '/analyze' ? (
          <Link to="/analyze" className="btn-primary">
            <Plus className="h-4 w-4" aria-hidden /> <span className="hidden sm:inline">New analysis</span>
          </Link>
        ) : null}
      </div>
    </header>
  )
}

export default function AppShell() {
  const [drawer, setDrawer] = useState(false)
  const location = useLocation()

  useEffect(() => setDrawer(false), [location.pathname])
  useEffect(() => {
    if (!drawer) return
    const onKey = (e) => e.key === 'Escape' && setDrawer(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [drawer])

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-slate-200 bg-white lg:block">
        <SidebarContent />
      </aside>

      {/* Mobile drawer */}
      {drawer ? (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" onClick={() => setDrawer(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 max-w-[85%] animate-fadeIn bg-white shadow-2xl">
            <button
              onClick={() => setDrawer(false)}
              className="absolute right-3 top-4 rounded-md p-2 text-slate-500 hover:bg-slate-100"
              aria-label="Close menu"
            >
              <X className="h-5 w-5" />
            </button>
            <SidebarContent onNavigate={() => setDrawer(false)} />
          </aside>
        </div>
      ) : null}

      <div className="lg:pl-64">
        <TopBar onMenu={() => setDrawer(true)} />
        <main className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
