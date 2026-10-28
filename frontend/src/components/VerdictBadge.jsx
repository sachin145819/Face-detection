import { verdictMeta } from '../lib/verdict.js'

export default function VerdictBadge({ verdict, size = 'md' }) {
  const m = verdictMeta(verdict)
  const Icon = m.icon
  const sizes = {
    sm: 'px-2 py-0.5 text-xs gap-1',
    md: 'px-2.5 py-1 text-xs gap-1.5',
    lg: 'px-4 py-2 text-base gap-2',
  }
  return (
    <span className={`inline-flex items-center whitespace-nowrap rounded-full font-semibold ring-1 ring-inset ${m.soft} ${sizes[size]}`}>
      <Icon className={size === 'lg' ? 'h-5 w-5' : 'h-3.5 w-3.5'} aria-hidden />
      {m.label}
    </span>
  )
}
