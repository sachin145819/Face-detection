import { ShieldCheck, Flame, FileText } from 'lucide-react'
import Logo from '../components/Logo.jsx'

export default function AuthLayout({ title, subtitle, children, footer }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[1fr_1.1fr]">
      <div className="dark-surface relative hidden overflow-hidden bg-navy-900 p-12 text-white lg:flex lg:flex-col">
        <div className="grid-bg absolute inset-0" aria-hidden />
        <div className="absolute -left-40 top-1/3 h-96 w-[520px] rounded-full bg-cyan-500/15 blur-[110px]" aria-hidden />
        <div className="relative"><Logo /></div>
        <div className="relative my-auto max-w-md">
          <h2 className="text-3xl font-semibold leading-tight tracking-tight text-white">
            Forensic-grade image verification, explained.
          </h2>
          <p className="mt-4 text-slate-400">
            Detect deepfakes, AI-generated images and manipulation, with the evidence to back every verdict.
          </p>
          <ul className="mt-10 space-y-5 text-sm text-slate-300">
            {[
              [ShieldCheck, 'Authenticity score fused from six forensic signals'],
              [Flame, 'Heatmaps and suspicious-region evidence'],
              [FileText, 'One-click forensic PDF reports'],
            ].map(([Icon, t]) => (
              <li key={t} className="flex items-center gap-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-cyan-300">
                  <Icon className="h-4 w-4" aria-hidden />
                </span>
                {t}
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-slate-500">GL Bajaj Institute of Technology &amp; Management · Mini Project 2026–27</p>
      </div>
      <div className="flex flex-col bg-white">
        <div className="border-b border-slate-200 px-4 py-4 lg:hidden"><Logo dark={false} /></div>
        <div className="flex flex-1 items-center justify-center px-4 py-12 sm:px-6">
          <div className="w-full max-w-sm animate-fadeIn">
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
            {subtitle ? <p className="mt-2 text-sm text-slate-500">{subtitle}</p> : null}
            <div className="mt-8">{children}</div>
            {footer ? <div className="mt-8 text-center text-sm text-slate-500">{footer}</div> : null}
          </div>
        </div>
      </div>
    </div>
  )
}
