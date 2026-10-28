import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Search, Trash2, ScanSearch, Images, AlertTriangle, ExternalLink, X, Image as ImageIcon, Film, Layers } from 'lucide-react'
import PageHeader from '../components/PageHeader.jsx'
import VerdictBadge from '../components/VerdictBadge.jsx'
import Pagination from '../components/Pagination.jsx'
import EmptyState from '../components/EmptyState.jsx'
import ConfirmDialog from '../components/ConfirmDialog.jsx'
import { Thumb, VideoTag } from '../components/HistoryRow.jsx'
import { historyApi, imagesApi, videosApi } from '../api/index.js'
import { isVideoItem, itemKey, resultPath } from '../lib/media.js'
import { errorMessage } from '../api/client.js'
import { useToast } from '../context/ToastContext.jsx'
import useDebounce from '../lib/useDebounce.js'
import { VERDICTS, VERDICT_KEYS, scoreColor } from '../lib/verdict.js'
import { formatDate, round } from '../lib/format.js'

const PAGE_SIZE = 10

const MEDIA = [
  { key: '', label: 'All', icon: Layers },
  { key: 'image', label: 'Images', icon: ImageIcon },
  { key: 'video', label: 'Videos', icon: Film },
]

function MediaFilter({ value, onChange }) {
  return (
    <div className="inline-flex shrink-0 rounded-lg bg-slate-100 p-1" role="radiogroup" aria-label="Filter by media type">
      {MEDIA.map(({ key, label, icon: Icon }) => {
        const active = value === key
        return (
          <button
            key={key || 'all'}
            role="radio"
            aria-checked={active}
            onClick={() => onChange(key)}
            className={`inline-flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition sm:flex-none ${
              active ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            <Icon className={`h-3.5 w-3.5 ${active ? 'text-cyan-600' : ''}`} aria-hidden /> {label}
          </button>
        )
      })}
    </div>
  )
}

export default function History() {
  const toast = useToast()
  const [q, setQ] = useState('')
  const [verdict, setVerdict] = useState('')
  const [media, setMedia] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState({ items: [], total: 0, page: 1, page_size: PAGE_SIZE })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [toDelete, setToDelete] = useState(null)
  const [deleting, setDeleting] = useState(false)
  const debouncedQ = useDebounce(q.trim(), 350)

  useEffect(() => setPage(1), [debouncedQ, verdict, media])

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    return historyApi
      .list({ q: debouncedQ, verdict, media, page, page_size: PAGE_SIZE })
      .then(setData)
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false))
  }, [debouncedQ, verdict, media, page])

  useEffect(() => {
    load()
  }, [load])

  const confirmDelete = async () => {
    if (!toDelete) return
    setDeleting(true)
    try {
      if (isVideoItem(toDelete)) await videosApi.remove(toDelete.video_id)
      else await imagesApi.remove(toDelete.image_id)
      toast.success(`Deleted “${toDelete.original_filename}”`)
      setToDelete(null)
      if (data.items.length === 1 && page > 1) setPage((p) => p - 1)
      else load()
    } catch (e) {
      toast.error(errorMessage(e, `Could not delete the ${isVideoItem(toDelete) ? 'video' : 'image'}.`))
    } finally {
      setDeleting(false)
    }
  }

  const filtered = Boolean(debouncedQ || verdict || media)
  const items = data.items || []

  return (
    <>
      <PageHeader
        eyebrow="Archive"
        title="Analysis history"
        subtitle="Search, filter and revisit every image and video you've analysed."
      />

      <div className="card">
        <div className="flex flex-col gap-3 border-b border-slate-100 p-4 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search by filename…"
              className="input pl-9"
              aria-label="Search by filename"
            />
          </div>
          <select value={verdict} onChange={(e) => setVerdict(e.target.value)} className="input sm:w-52" aria-label="Filter by verdict">
            <option value="">All verdicts</option>
            {VERDICT_KEYS.map((k) => <option key={k} value={k}>{VERDICTS[k].label}</option>)}
          </select>
          <MediaFilter value={media} onChange={setMedia} />
          {filtered ? (
            <button className="btn-ghost text-xs" onClick={() => { setQ(''); setVerdict(''); setMedia('') }}>
              <X className="h-3.5 w-3.5" aria-hidden /> Clear
            </button>
          ) : null}
        </div>

        {/* Verdict quick filters */}
        <div className="flex flex-wrap gap-2 border-b border-slate-100 px-4 py-3">
          <button onClick={() => setVerdict('')} className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset transition ${!verdict ? 'bg-slate-900 text-white ring-slate-900' : 'text-slate-600 ring-slate-200 hover:bg-slate-50'}`}>All</button>
          {VERDICT_KEYS.map((k) => (
            <button
              key={k}
              onClick={() => setVerdict(verdict === k ? '' : k)}
              aria-pressed={verdict === k}
              className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset transition ${verdict === k ? VERDICTS[k].soft : 'text-slate-600 ring-slate-200 hover:bg-slate-50'}`}
            >
              {VERDICTS[k].label}
            </button>
          ))}
        </div>

        {loading && !items.length ? (
          <div className="space-y-3 p-4">
            {Array.from({ length: 5 }).map((_, i) => <div key={i} className="skeleton h-14" />)}
          </div>
        ) : error ? (
          <EmptyState icon={AlertTriangle} title="Couldn't load history" message={error} action={<button className="btn-dark" onClick={load}>Try again</button>} />
        ) : !items.length ? (
          filtered ? (
            <EmptyState icon={Search} title="No matching analyses" message="Try a different filename, verdict or media filter." />
          ) : (
            <EmptyState
              icon={Images}
              title="No analyses yet"
              message="Images and videos you analyse will appear here with their verdict and score."
              action={<Link to="/analyze" className="btn-primary"><ScanSearch className="h-4 w-4" aria-hidden /> Analyze your first image</Link>}
            />
          )
        ) : (
          <div className={`transition-opacity ${loading ? 'opacity-60' : ''}`}>
            {/* Desktop table */}
            <table className="hidden w-full text-left text-sm md:table">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-3 font-semibold">File</th>
                  <th className="px-4 py-3 font-semibold">Verdict</th>
                  <th className="px-4 py-3 font-semibold">Score</th>
                  <th className="px-4 py-3 font-semibold">Confidence</th>
                  <th className="px-4 py-3 font-semibold">Date</th>
                  <th className="px-4 py-3 text-right font-semibold"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((it) => (
                  <tr key={itemKey(it)} className="group hover:bg-slate-50/60">
                    <td className="px-4 py-3">
                      <Link to={resultPath(it)} className="flex items-center gap-3 rounded-lg">
                        <Thumb url={it.thumbnail_url} alt={it.original_filename} video={isVideoItem(it)} />
                        <span className="max-w-[260px] truncate font-medium text-slate-800 group-hover:text-cyan-700">{it.original_filename}</span>
                        {isVideoItem(it) ? <VideoTag /> : null}
                      </Link>
                    </td>
                    <td className="px-4 py-3"><VerdictBadge verdict={it.verdict} /></td>
                    <td className="px-4 py-3">
                      <span className="font-serif text-lg font-bold tabular-nums" style={{ color: scoreColor(it.authenticity_score) }}>{round(it.authenticity_score)}</span>
                      <span className="text-xs text-slate-400">/100</span>
                    </td>
                    <td className="px-4 py-3 tabular-nums text-slate-600">{it.confidence != null ? `${Math.round(it.confidence * 100)}%` : '—'}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-slate-500">{formatDate(it.created_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-1">
                        <Link to={resultPath(it)} className="btn-ghost px-2.5 py-1.5 text-xs" aria-label={`Open result for ${it.original_filename}`}>
                          <ExternalLink className="h-4 w-4" aria-hidden /> Open
                        </Link>
                        <button onClick={() => setToDelete(it)} className="btn-ghost px-2.5 py-1.5 text-xs text-red-600 hover:bg-red-50" aria-label={`Delete ${it.original_filename}`}>
                          <Trash2 className="h-4 w-4" aria-hidden />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Mobile cards */}
            <ul className="divide-y divide-slate-100 md:hidden">
              {items.map((it) => (
                <li key={itemKey(it)} className="flex items-center gap-3 px-4 py-3">
                  <Link to={resultPath(it)} className="flex min-w-0 flex-1 items-center gap-3 rounded-lg">
                    <Thumb url={it.thumbnail_url} alt={it.original_filename} className="h-14 w-14" video={isVideoItem(it)} />
                    <div className="min-w-0">
                      <p className="flex min-w-0 items-center gap-2">
                        <span className="truncate text-sm font-medium text-slate-800">{it.original_filename}</span>
                        {isVideoItem(it) ? <VideoTag /> : null}
                      </p>
                      <div className="mt-1 flex items-center gap-2">
                        <VerdictBadge verdict={it.verdict} size="sm" />
                        <span className="text-xs font-semibold tabular-nums" style={{ color: scoreColor(it.authenticity_score) }}>{round(it.authenticity_score)}/100</span>
                      </div>
                      <p className="mt-0.5 text-[11px] text-slate-400">{formatDate(it.created_at)}</p>
                    </div>
                  </Link>
                  <button onClick={() => setToDelete(it)} className="rounded-lg p-2 text-red-600 hover:bg-red-50" aria-label={`Delete ${it.original_filename}`}>
                    <Trash2 className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>

            <Pagination page={page} pageSize={PAGE_SIZE} total={data.total || 0} onChange={setPage} />
          </div>
        )}
      </div>

      <ConfirmDialog
        open={Boolean(toDelete)}
        title={isVideoItem(toDelete) ? 'Delete this video?' : 'Delete this image?'}
        message={
          toDelete
            ? isVideoItem(toDelete)
              ? `“${toDelete.original_filename}” and all of its analyses, frames and reports will be permanently deleted.`
              : `“${toDelete.original_filename}” and all of its analyses, restorations and reports will be permanently deleted.`
            : ''
        }
        confirmLabel="Delete"
        busy={deleting}
        onCancel={() => setToDelete(null)}
        onConfirm={confirmDelete}
      />
    </>
  )
}
