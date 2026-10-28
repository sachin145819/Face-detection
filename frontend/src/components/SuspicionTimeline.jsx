import { useMemo } from 'react'
import {
  Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { formatTimestamp } from '../lib/video.js'

export const SERIES = [
  { key: 'suspicion', label: 'Suspicion (fused)', color: '#2557eb' },
  { key: 'deepfake_probability', label: 'Face deepfake', color: '#dc2626', dash: '5 4' },
  { key: 'ai_generated_probability', label: 'AI-generated', color: '#8b5cf6', dash: '2 3' },
]

function pctOrNa(v) {
  return v == null ? 'n/a' : `${Math.round(v * 100)}%`
}

function TimelineTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-lg border border-white/10 bg-navy-900 px-3 py-2 text-xs text-slate-200 shadow-xl">
      <p className="mb-1 font-semibold text-white">
        Frame {d.index + 1} · {formatTimestamp(d.timestamp_s)}
      </p>
      {SERIES.map((s) => (
        <p key={s.key} className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: s.color }} />
          {s.label}
          <span className="ml-auto pl-4 font-semibold tabular-nums">{pctOrNa(d[s.key])}</span>
        </p>
      ))}
      <p className="mt-1 border-t border-white/10 pt-1 text-slate-400">
        {d.faces?.length ? `${d.faces.length} face${d.faces.length > 1 ? 's' : ''}` : 'No faces'} · click to inspect
      </p>
    </div>
  )
}

/** Per-frame suspicion over time. Clicking anywhere selects the nearest sampled frame. */
export default function SuspicionTimeline({ frames = [], duration, selected, playhead, onSelect }) {
  const data = useMemo(
    () =>
      frames.map((f, i) => ({
        ...f,
        index: f.index ?? i,
        suspicion: f.suspicion ?? null,
        deepfake_probability: f.deepfake_probability ?? null,
        ai_generated_probability: f.ai_generated_probability ?? null,
      })),
    [frames],
  )
  const maxT = Math.max(duration || 0, data.length ? data[data.length - 1].timestamp_s : 0) || 1
  const sel = data[selected]

  const handleClick = (state) => {
    if (!state || !onSelect) return
    const i = state.activeTooltipIndex
    if (i != null && i >= 0 && i < data.length) onSelect(i)
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-slate-600" aria-hidden>
        {SERIES.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1.5">
            <svg width="18" height="8" className="shrink-0">
              <line x1="1" y1="4" x2="17" y2="4" stroke={s.color} strokeWidth="2" strokeDasharray={s.dash} strokeLinecap="round" />
            </svg>
            {s.label}
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-3.5 rounded-sm bg-amber-100 ring-1 ring-inset ring-amber-200" /> Borderline zone
        </span>
      </div>
      <div className="h-56 sm:h-64" role="img" aria-label="Suspicion timeline chart. Use the frame strip below for an accessible list of frames.">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 12, left: -18, bottom: 0 }} onClick={handleClick} style={{ cursor: 'pointer' }}>
            <defs>
              <linearGradient id="suspFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#2557eb" stopOpacity={0.22} />
                <stop offset="100%" stopColor="#2557eb" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
            <ReferenceArea y1={0.33} y2={0.66} fill="#fef3c7" fillOpacity={0.55} ifOverflow="extendDomain" />
            <XAxis
              dataKey="timestamp_s"
              type="number"
              domain={[0, maxT]}
              tickFormatter={(t) => formatTimestamp(t).replace(/\.\d$/, '')}
              tickLine={false}
              axisLine={{ stroke: '#e2e8f0' }}
              tick={{ fontSize: 11, fill: '#64748b' }}
              minTickGap={24}
            />
            <YAxis
              domain={[0, 1]}
              ticks={[0, 0.25, 0.5, 0.75, 1]}
              tickFormatter={(v) => `${Math.round(v * 100)}%`}
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 11, fill: '#64748b' }}
            />
            <Tooltip content={<TimelineTooltip />} cursor={{ stroke: '#94a3b8', strokeDasharray: '3 3' }} />
            {sel ? <ReferenceLine x={sel.timestamp_s} stroke="#0f172a" strokeWidth={1.5} /> : null}
            {playhead != null && playhead > 0 ? <ReferenceLine x={playhead} stroke="#2557eb" strokeOpacity={0.45} strokeWidth={1} /> : null}
            <Area
              type="monotone"
              dataKey="suspicion"
              stroke="#2557eb"
              strokeWidth={2}
              fill="url(#suspFill)"
              connectNulls={false}
              isAnimationActive={false}
              dot={(p) => {
                const { cx, cy, index } = p
                if (cx == null || cy == null) return <g key={`d${index}`} />
                const isSel = index === selected
                return (
                  <circle
                    key={`d${index}`}
                    cx={cx}
                    cy={cy}
                    r={isSel ? 6 : 3.5}
                    fill={isSel ? '#2557eb' : '#fff'}
                    stroke={isSel ? '#fff' : '#2557eb'}
                    strokeWidth={2}
                  />
                )
              }}
              activeDot={{ r: 6, stroke: '#fff', strokeWidth: 2, fill: '#2557eb' }}
            />
            {SERIES.slice(1).map((s) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                stroke={s.color}
                strokeWidth={2}
                strokeDasharray={s.dash}
                dot={false}
                activeDot={{ r: 4, stroke: '#fff', strokeWidth: 2, fill: s.color }}
                connectNulls={false}
                isAnimationActive={false}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
