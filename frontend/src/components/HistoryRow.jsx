import { Link } from 'react-router-dom'
import { ChevronRight, ImageOff, Film } from 'lucide-react'
import { useState } from 'react'
import VerdictBadge from './VerdictBadge.jsx'
import { withToken } from '../lib/files.js'
import { formatDate, round } from '../lib/format.js'
import { scoreColor } from '../lib/verdict.js'
import { isVideoItem, resultPath } from '../lib/media.js'

export function Thumb({ url, alt, className = 'h-12 w-12', video = false }) {
  const [err, setErr] = useState(false)
  const Fallback = video ? Film : ImageOff
  return (
    <div className={`relative shrink-0 ${className}`}>
      {!url || err ? (
        <div className="flex h-full w-full items-center justify-center rounded-lg bg-slate-100 text-slate-400">
          <Fallback className="h-5 w-5" aria-hidden />
        </div>
      ) : (
        <img src={withToken(url)} alt={alt} loading="lazy" onError={() => setErr(true)} className="h-full w-full rounded-lg object-cover ring-1 ring-slate-200" />
      )}
      {video && url && !err ? (
        <span className="absolute bottom-0.5 right-0.5 flex h-4 w-4 items-center justify-center rounded bg-navy-900/85 text-white" title="Video">
          <Film className="h-2.5 w-2.5" aria-hidden />
        </span>
      ) : null}
    </div>
  )
}

export function VideoTag() {
  return (
    <span className="inline-flex shrink-0 items-center gap-1 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-600">
      <Film className="h-3 w-3" aria-hidden /> Video
    </span>
  )
}

export default function HistoryRow({ item }) {
  const video = isVideoItem(item)
  return (
    <Link
      to={resultPath(item)}
      className="group flex items-center gap-3 rounded-xl px-3 py-2.5 transition hover:bg-slate-50 focus-visible:bg-slate-50"
    >
      <Thumb url={item.thumbnail_url} alt={item.original_filename} video={video} />
      <div className="min-w-0 flex-1">
        <p className="flex min-w-0 items-center gap-2">
          <span className="truncate text-sm font-medium text-slate-800">{item.original_filename}</span>
          {video ? <VideoTag /> : null}
        </p>
        <p className="text-xs text-slate-500">{formatDate(item.created_at)}</p>
      </div>
      <div className="hidden text-right sm:block">
        <span className="font-serif text-lg font-bold tabular-nums" style={{ color: scoreColor(item.authenticity_score) }}>
          {round(item.authenticity_score)}
        </span>
        <span className="text-xs text-slate-400">/100</span>
      </div>
      <VerdictBadge verdict={item.verdict} size="sm" />
      <ChevronRight className="h-4 w-4 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-slate-500" aria-hidden />
    </Link>
  )
}
