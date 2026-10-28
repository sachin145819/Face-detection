import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { Activity, Gauge, ScanSearch, RefreshCw, Images, History as HistoryIcon, AlertTriangle, Film } from 'lucide-react'
import PageHeader from '../components/PageHeader.jsx'
import EmptyState from '../components/EmptyState.jsx'
import HistoryRow from '../components/HistoryRow.jsx'
import { itemKey } from '../lib/media.js'
import { dashboardApi } from '../api/index.js'
import { errorMessage } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'
import { VERDICTS, VERDICT_KEYS, scoreColor } from '../lib/verdict.js'
import { round, weekdayLabel } from '../lib/format.js'

function StatTile({ icon: Icon, label, value, sub, accent = 'text-cyan-600 bg-cyan-50', valueColor }) {
  return (
    <div className="card flex items-start gap-4 p-5">
      <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${accent}`}>
        <Icon className="h-5 w-5" aria-hidden />
      </div>
      <div className="min-w-0">
        <p className="text-xs font-medium uppercase tracking-wider text-slate-500">{label}</p>
        <p className="mt-1 font-serif text-3xl font-bold tabular-nums text-slate-900" style={valueColor ? { color: valueColor } : undefined}>
          {value}
        </p>
        {sub ? <p className="mt-0.5 text-xs text-slate-500">{sub}</p> : null}
      </div>
    </div>
  )
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {[0, 1, 2].map((i) => <div key={i} className="skeleton h-28" />)}
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-20" />)}
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="skeleton h-80 lg:col-span-2" />
        <div className="skeleton h-80" />
      </div>
    </div>
  )
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const total = payload.reduce((s, p) => s + (p.value || 0), 0)
  return (
    <div className="rounded-xl border border-white/10 bg-navy-900 px-3 py-2 text-xs text-slate-200 shadow-xl">
      <p className="mb-1 font-semibold text-white">{label}</p>
      {payload.slice().reverse().map((p) => (
        <p key={p.dataKey} className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
          {VERDICTS[p.dataKey]?.label}: <span className="ml-auto font-semibold tabular-nums">{p.value}</span>
        </p>
      ))}
      <p className="mt-1 border-t border-white/10 pt-1 text-slate-400">Total: {total}</p>
    </div>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    dashboardApi
      .stats()
      .then(setStats)
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(load, [load])

  const firstName = user?.name?.split(' ')[0] || 'there'
  const header = (
    <PageHeader
      eyebrow="Overview"
      title={`Welcome, ${firstName}`}
      subtitle="Your image and video forensics activity at a glance."
      actions={
        <>
          <button className="btn-outline" onClick={load} disabled={loading} aria-label="Refresh">
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} aria-hidden />
          </button>
        </>
      }
    />
  )

  if (loading && !stats) return <>{header}<DashboardSkeleton /></>

  if (error && !stats) {
    return (
      <>
        {header}
        <div className="card">
          <EmptyState icon={AlertTriangle} title="Couldn't load your dashboard" message={error} action={<button className="btn-dark" onClick={load}>Try again</button>} />
        </div>
      </>
    )
  }

  const byVerdict = stats?.by_verdict || {}
  const total = stats?.total_analyses || 0
  const trend = (stats?.trend || []).map((d) => ({ ...d, label: weekdayLabel(d.date) }))
  const pieData = VERDICT_KEYS.map((k) => ({ key: k, name: VERDICTS[k].label, value: byVerdict[k] || 0 })).filter((d) => d.value > 0)
  const flagged = total - (byVerdict.authentic || 0)
  // Older backends don't send video fields — fall back to the image-only subtitle.
  const byMedia = stats?.by_media
  const hasVideoStats = byMedia != null || stats?.total_videos != null
  const imageCount = byMedia?.image ?? Math.max(0, total - (byMedia?.video ?? 0))
  const videoCount = byMedia?.video ?? 0
  const totalSub = hasVideoStats
    ? `${imageCount} image${imageCount === 1 ? '' : 's'} · ${videoCount} video${videoCount === 1 ? '' : 's'}`
    : `${stats?.total_images ?? 0} images uploaded`

  if (total === 0) {
    return (
      <>
        {header}
        <div className="dark-surface relative overflow-hidden rounded-2xl bg-navy-900 shadow-card">
          <div className="grid-bg absolute inset-0" aria-hidden />
          <div className="relative grid items-center gap-8 p-8 md:grid-cols-2 md:p-12">
            <div>
              <h2 className="font-serif text-3xl font-bold text-white">Run your first analysis</h2>
              <p className="mt-3 text-slate-300">
                Upload a JPEG, PNG or WebP image — or a short video. TruthLens will check it for deepfakes, AI generation and
                manipulation, and explain every finding with heatmaps, region evidence and a frame-by-frame timeline.
              </p>
              <div className="mt-6 flex flex-wrap gap-3">
                <Link to="/analyze" className="btn-primary px-6 py-3 text-base">
                  <ScanSearch className="h-5 w-5" aria-hidden /> Analyze an image
                </Link>
                <Link to="/analyze?type=video" className="btn border border-white/15 px-6 py-3 text-base text-white hover:bg-white/10">
                  <Film className="h-5 w-5" aria-hidden /> Analyze a video
                </Link>
              </div>
            </div>
            <ol className="space-y-3">
              {['Drop an image into the upload zone', 'Watch the five-stage forensic pipeline', 'Explore the verdict, heatmap & signals', 'Download the PDF report'].map((t, i) => (
                <li key={t} className="flex items-center gap-3 rounded-xl bg-white/5 px-4 py-3 text-sm text-slate-200 ring-1 ring-inset ring-white/10">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-cyan-400 text-xs font-bold text-navy-900">{i + 1}</span>
                  {t}
                </li>
              ))}
            </ol>
          </div>
        </div>
      </>
    )
  }

  return (
    <>
      {header}
      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <StatTile icon={Activity} label="Total analyses" value={total} sub={totalSub} />
          <StatTile
            icon={Gauge}
            label="Avg authenticity"
            value={round(stats.avg_authenticity_score)}
            sub="out of 100"
            accent="text-violet-600 bg-violet-50"
            valueColor={scoreColor(stats.avg_authenticity_score)}
          />
          <StatTile icon={AlertTriangle} label="Flagged" value={flagged} sub={`${total ? Math.round((flagged / total) * 100) : 0}% of analyses`} accent="text-red-600 bg-red-50" />
        </div>

        <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
          {VERDICT_KEYS.map((k) => {
            const m = VERDICTS[k]
            const Icon = m.icon
            const n = byVerdict[k] || 0
            return (
              <div key={k} className="card p-4">
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-2 text-sm font-medium text-slate-600">
                    <Icon className="h-4 w-4" style={{ color: m.color }} aria-hidden /> {m.label}
                  </span>
                  <span className="font-serif text-2xl font-bold tabular-nums text-slate-900">{n}</span>
                </div>
                <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full transition-all" style={{ width: `${total ? (n / total) * 100 : 0}%`, background: m.color }} />
                </div>
              </div>
            )
          })}
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="card p-5 lg:col-span-2">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="section-title">Last 7 days</h2>
              <span className="text-xs text-slate-500">Analyses per day by verdict</span>
            </div>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={trend} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                  <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: '#64748b' }} />
                  <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: '#64748b' }} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(34,211,238,0.08)' }} />
                  <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} formatter={(v) => VERDICTS[v]?.label || v} />
                  {VERDICT_KEYS.map((k, i) => (
                    <Bar key={k} dataKey={k} stackId="v" fill={VERDICTS[k].color} radius={i === VERDICT_KEYS.length - 1 ? [6, 6, 0, 0] : [0, 0, 0, 0]} maxBarSize={44} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card p-5">
            <h2 className="section-title mb-4">Verdict distribution</h2>
            <div className="relative h-56">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={pieData} dataKey="value" nameKey="name" innerRadius="62%" outerRadius="90%" paddingAngle={pieData.length > 1 ? 3 : 0} stroke="none">
                    {pieData.map((d) => <Cell key={d.key} fill={VERDICTS[d.key].color} />)}
                  </Pie>
                  <Tooltip formatter={(v, n) => [v, n]} contentStyle={{ borderRadius: 12, fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                <span className="font-serif text-3xl font-bold text-slate-900">{total}</span>
                <span className="text-xs text-slate-500">analyses</span>
              </div>
            </div>
            <ul className="mt-4 space-y-2 text-sm">
              {VERDICT_KEYS.map((k) => (
                <li key={k} className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: VERDICTS[k].color }} />
                  <span className="text-slate-600">{VERDICTS[k].label}</span>
                  <span className="ml-auto font-medium tabular-nums text-slate-800">
                    {byVerdict[k] || 0} <span className="text-slate-400">({total ? Math.round(((byVerdict[k] || 0) / total) * 100) : 0}%)</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
            <h2 className="section-title">Recent analyses</h2>
            <Link to="/history" className="inline-flex items-center gap-1 rounded text-sm font-medium text-cyan-700 hover:underline">
              <HistoryIcon className="h-4 w-4" aria-hidden /> View all
            </Link>
          </div>
          {stats.recent?.length ? (
            <div className="divide-y divide-slate-100 p-2">
              {stats.recent.map((it) => <HistoryRow key={itemKey(it)} item={it} />)}
            </div>
          ) : (
            <EmptyState icon={Images} title="No recent analyses" message="Analyses you run will show up here." />
          )}
        </div>
      </div>
    </>
  )
}
