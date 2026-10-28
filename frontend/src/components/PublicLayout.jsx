import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import Logo from './Logo.jsx'
import { useAuth } from '../context/AuthContext.jsx'

export function PublicNav() {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const links = [
    { href: '/#problem', label: 'Problem' },
    { href: '/#features', label: 'Platform' },
    { href: '/#workflow', label: 'How it works' },
  ]
  return (
    <header className="dark-surface sticky top-0 z-40 border-b border-white/10 bg-navy-900/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-10">
          <Logo />
          <nav className="hidden items-center gap-7 md:flex" aria-label="Primary">
            {links.map((l) => (
              <a key={l.href} href={l.href} className="rounded text-sm text-slate-400 transition-colors hover:text-white">
                {l.label}
              </a>
            ))}
          </nav>
        </div>
        <div className="hidden items-center gap-2 md:flex">
          {user ? (
            <Link to="/dashboard" className="btn-primary">Open dashboard</Link>
          ) : (
            <>
              <Link to="/login" className="btn text-slate-300 hover:bg-white/10 hover:text-white">Sign in</Link>
              <Link to="/register" className="btn bg-white text-slate-900 hover:bg-slate-100">Get started</Link>
            </>
          )}
        </div>
        <button className="rounded-md p-2 text-slate-300 hover:bg-white/10 md:hidden" onClick={() => setOpen((o) => !o)} aria-label="Toggle menu" aria-expanded={open}>
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>
      {open ? (
        <div className="border-t border-white/10 px-4 pb-4 md:hidden">
          <nav className="flex flex-col py-2" aria-label="Mobile">
            {links.map((l) => (
              <a key={l.href} href={l.href} onClick={() => setOpen(false)} className="rounded px-2 py-2.5 text-sm text-slate-300 hover:text-white">
                {l.label}
              </a>
            ))}
          </nav>
          <div className="flex gap-2">
            {user ? (
              <Link to="/dashboard" className="btn-primary flex-1">Open dashboard</Link>
            ) : (
              <>
                <Link to="/login" className="btn flex-1 border border-white/15 text-white">Sign in</Link>
                <Link to="/register" className="btn flex-1 bg-white text-slate-900">Get started</Link>
              </>
            )}
          </div>
        </div>
      ) : null}
    </header>
  )
}

const FOOTER_COLS = [
  {
    title: 'Platform',
    links: [
      ['Features', '/#features'],
      ['How it works', '/#workflow'],
      ['API reference', '/docs'],
    ],
  },
  {
    title: 'Account',
    links: [
      ['Sign in', '/login'],
      ['Create account', '/register'],
      ['Dashboard', '/dashboard'],
    ],
  },
]

export function PublicFooter() {
  return (
    <footer className="border-t border-slate-200 bg-white">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-14 sm:px-6 md:grid-cols-4 lg:px-8">
        <div className="md:col-span-2">
          <Logo dark={false} />
          <p className="mt-4 max-w-sm text-sm leading-6 text-slate-500">
            AI-based image authenticity verification, deepfake detection and intelligent content restoration.
          </p>
          <p className="mt-4 text-xs text-slate-400">
            GL Bajaj Institute of Technology &amp; Management, Greater Noida · Dept. of CSE · Mini Project 2026–27
          </p>
        </div>
        {FOOTER_COLS.map((c) => (
          <div key={c.title}>
            <h3 className="text-sm font-semibold text-slate-900">{c.title}</h3>
            <ul className="mt-4 space-y-2.5">
              {c.links.map(([label, href]) => (
                <li key={label}>
                  <a href={href} className="text-sm text-slate-500 transition-colors hover:text-slate-900">{label}</a>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-slate-200">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-2 px-4 py-6 text-xs text-slate-400 sm:px-6 md:flex-row lg:px-8">
          <p>© 2026 TruthLens · Prince Tomar &amp; Team · Guided by Mr. Prasanna Dwivedi</p>
          <p>Probabilistic evidence, corroborated by human review — never a substitute for it.</p>
        </div>
      </div>
    </footer>
  )
}
