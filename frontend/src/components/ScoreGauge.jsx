import { scoreColor } from '../lib/verdict.js'

/** Radial gauge 0–100 drawn as a 270° SVG arc. */
export default function ScoreGauge({ score = 0, size = 180, label = 'Authenticity' }) {
  const value = Math.max(0, Math.min(100, Number(score) || 0))
  const stroke = 14
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const arc = c * 0.75
  const filled = arc * (value / 100)
  const color = scoreColor(value)
  return (
    <div className="relative inline-flex" style={{ width: size, height: size }} role="img" aria-label={`${label} score ${Math.round(value)} out of 100`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="rotate-[135deg]">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="#e2e8f0"
          strokeWidth={stroke}
          strokeDasharray={`${arc} ${c}`}
          strokeLinecap="round"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeDasharray={`${filled} ${c}`}
          strokeLinecap="round"
          style={{ transition: 'stroke-dasharray 1s ease-out' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-serif text-5xl font-bold leading-none" style={{ color }}>
          {Math.round(value)}
        </span>
        <span className="mt-1 text-xs font-medium uppercase tracking-wider text-slate-500">{label}</span>
        <span className="text-[10px] text-slate-400">out of 100</span>
      </div>
    </div>
  )
}
