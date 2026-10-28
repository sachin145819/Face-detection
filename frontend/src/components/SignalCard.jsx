import { FileSearch, Layers, Waves, Radio, ScanFace, Bot, Activity, Timer } from 'lucide-react'

const ICONS = { metadata: FileSearch, ela: Layers, noise: Waves, frequency: Radio, deepfake: ScanFace, ai_generated: Bot, temporal: Timer }

function barColor(s) {
  if (s >= 0.66) return '#dc2626'
  if (s >= 0.33) return '#f59e0b'
  return '#16a34a'
}

export default function SignalCard({ signal }) {
  const { key, label, score, weight, available, explanation } = signal
  const Icon = ICONS[key] || Activity
  const s = Math.max(0, Math.min(1, Number(score) || 0))
  return (
    <div className={`card flex flex-col p-4 ${available ? '' : 'opacity-60 grayscale'}`}>
      <div className="flex items-start gap-3">
        <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${available ? 'bg-cyan-50 text-cyan-600 ring-1 ring-inset ring-cyan-100' : 'bg-slate-100 text-slate-400'}`}>
          <Icon className="h-4 w-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-slate-900">{label || key}</p>
          <p className="text-xs text-slate-500">
            Weight {weight != null ? `${Math.round(weight * 100)}%` : '—'}
          </p>
        </div>
        {available ? (
          <span className="font-serif text-xl font-bold tabular-nums" style={{ color: barColor(s) }}>{Math.round(s * 100)}%</span>
        ) : (
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Unavailable</span>
        )}
      </div>
      <div className="mt-3">
        <div className="flex justify-between text-[11px] text-slate-400">
          <span>Suspicion</span>
          <span>{available ? (s >= 0.66 ? 'High' : s >= 0.33 ? 'Moderate' : 'Low') : 'n/a'}</span>
        </div>
        <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={available ? Math.round(s * 100) : undefined} aria-label={`${label} suspicion`}>
          {available ? <div className="h-full rounded-full transition-all duration-700" style={{ width: `${s * 100}%`, background: barColor(s) }} /> : null}
        </div>
      </div>
      {explanation ? <p className="mt-3 text-xs leading-relaxed text-slate-600">{explanation}</p> : null}
      {!available ? <p className="mt-2 text-xs italic text-slate-400">Model unavailable — excluded from the weighted score.</p> : null}
    </div>
  )
}
