import { useId } from 'react'
import { Link } from 'react-router-dom'

export function LogoMark({ className = 'h-8 w-8' }) {
  // Unique per instance: a gradient defined inside a hidden (display:none) copy can't be referenced.
  const gid = `tl-g-${useId().replace(/:/g, '')}`
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#3b72f6" />
          <stop offset="1" stopColor="#6d4aff" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="16" fill={`url(#${gid})`} />
      <path
        d="M32 12 L48 18.5 V31 C48 41.5 41 48.5 32 52 C23 48.5 16 41.5 16 31 V18.5 Z"
        fill="none"
        stroke="#fff"
        strokeWidth="3.5"
        strokeLinejoin="round"
      />
      <circle cx="31" cy="30.5" r="7" fill="none" stroke="#fff" strokeWidth="3.5" />
      <path d="M36.5 36 L41.5 41" stroke="#fff" strokeWidth="3.5" strokeLinecap="round" />
    </svg>
  )
}

export default function Logo({ to = '/', dark = true, className = '' }) {
  return (
    <Link to={to} className={`group inline-flex items-center gap-2.5 rounded-lg ${className}`} aria-label="TruthLens home">
      <LogoMark />
      <span className={`text-[17px] font-semibold tracking-tight ${dark ? 'text-white' : 'text-slate-900'}`}>
        TruthLens
      </span>
    </Link>
  )
}
