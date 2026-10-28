import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  AlertTriangle, ArrowLeft, Clock, Cpu, Download, FileText, ScanFace, Info, RefreshCw, Lightbulb, Film, Activity,
  ImageOff, Flame, ChevronLeft, ChevronRight, FileSearch, ChevronDown, Sparkles, VideoOff,
} from 'lucide-react'
import VerdictBadge from '../components/VerdictBadge.jsx'
import ScoreGauge from '../components/ScoreGauge.jsx'
import SignalCard from '../components/SignalCard.jsx'
import BoxOverlay from '../components/BoxOverlay.jsx'
import CompareSlider from '../components/CompareSlider.jsx'
import SuspicionTimeline from '../components/SuspicionTimeline.jsx'
import Disclaimer from '../components/Disclaimer.jsx'
import EmptyState from '../components/EmptyState.jsx'
import { videoAnalysesApi } from '../api/index.js'
import { errorMessage } from '../api/client.js'
import { withToken } from '../lib/files.js'
import { formatBytes, formatDate, formatMs, pct } from '../lib/format.js'
import { verdictMeta } from '../lib/verdict.js'
import { formatDuration, formatFps, formatTimestamp, suspicionColor } from '../lib/video.js'

const VIDEO_BLURBS = {
  authentic: 'No significant evidence of manipulation was found across the sampled frames.',
  manipulated: 'Parts of this video appear to have been edited.',
  deepfake: 'Faces in this video show signs of synthetic face manipulation.',
  ai_generated: 'Frames in this video show characteristics of generative AI models.',
}

function ResultSkeleton() {
  return (
    <div className="space-y-6">
      <div className="skeleton h-10 w-2/3" />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="skeleton h-[460px]" />
        <div className="skeleton h-[460px] lg:col-span-2" />
      </div>
      <div className="skeleton h-40" />
    </div>
  )
}

function FrameImage({ src, alt, className = '' }) {
  const [err, setErr] = useState(false)
  if (!src || err) {
    return (
      <div className={`flex aspect-video w-full items-center justify-center bg-slate-100 text-slate-400 ${className}`}>
        <ImageOff className="h-5 w-5" aria-hidden />
      </div>
    )
  }
  return <img src={src} alt={alt} loading="lazy" onError={() => setErr(true)} className={`block aspect-video w-full object-cover ${className}`} draggable={false} />
}

/* ---------------------------------------------------------------- player */

function VideoPlayer({ src, mime, videoRef, onTime, onUnsupported, unsupported }) {
  if (unsupported) {
    return (
      <div className="flex aspect-video w-full flex-col items-center justify-center gap-2 bg-navy-900 px-6 text-center">
        <VideoOff className="h-9 w-9 text-slate-400" aria-hidden />
        <p className="text-sm font-medium text-white">This browser can't play this video format</p>
        <p className="max-w-sm text-xs text-slate-400">
          {mime ? `${mime} video` : 'This format'} can't be played here — formats such as AVI and MKV often aren't supported by browsers. The
          analysis is complete: use the timeline and sampled frames below to inspect it.
        </p>
      </div>
    )
  }
  return (
    <video
      ref={videoRef}
      src={src}
      controls
      playsInline
      preload="metadata"
      className="block aspect-video w-full bg-navy-900 object-contain"
      onTimeUpdate={(e) => onTime(e.currentTarget.currentTime)}
      onSeeked={(e) => onTime(e.currentTarget.currentTime)}
      onLoadedMetadata={(e) => {
        // Audio-only playback means the video codec isn't supported.
        if (!e.currentTarget.videoWidth) onUnsupported()
      }}
      onError={onUnsupported}
    >
      <track kind="captions" />
    </video>
  )
}

/* ------------------------------------------------------------ frame strip */

function FrameStrip({ frames, topFrames, selected, onSelect }) {
  const topRank = new Map(topFrames.map((idx, r) => [idx, r]))
  const listRef = useRef(null)
  // On mobile the strip scrolls horizontally: keep the selected frame in view.
  useEffect(() => {
    const ul = listRef.current
    const li = ul?.children?.[selected]
    if (!ul || !li || ul.scrollWidth <= ul.clientWidth) return
    ul.scrollTo({ left: li.offsetLeft - ul.clientWidth / 2 + li.clientWidth / 2, behavior: 'smooth' })
  }, [selected])
  return (
    <ul ref={listRef} className="relative -mx-4 flex snap-x gap-3 overflow-x-auto px-4 pb-2 sm:mx-0 sm:grid sm:grid-cols-4 sm:overflow-visible sm:px-0 sm:pb-0 lg:grid-cols-6 xl:grid-cols-8" aria-label="Sampled frames">
      {frames.map((f, i) => {
        const s = f.suspicion
        const isSel = i === selected
        const isTop = topRank.has(i)
        return (
          <li key={i} className="w-32 shrink-0 snap-start sm:w-auto">
            <button
              onClick={() => onSelect(i)}
              aria-pressed={isSel}
              aria-label={`Frame ${i + 1} at ${formatTimestamp(f.timestamp_s)}, suspicion ${pct(s)}${isTop ? ', most suspicious' : ''}`}
              className={`group block w-full overflow-hidden rounded-lg bg-white text-left ring-1 transition ${
                isSel ? 'ring-2 ring-cyan-600 shadow-glow' : isTop ? 'ring-red-300 hover:ring-red-400' : 'ring-slate-200 hover:ring-slate-300'
              }`}
            >
              <div className="relative">
                <FrameImage src={withToken(f.thumbnail_url)} alt="" />
                <span className="absolute bottom-1 left-1 rounded bg-navy-900/80 px-1.5 py-0.5 font-mono text-[10px] font-medium text-white">
                  {formatTimestamp(f.timestamp_s)}
                </span>
                {isTop ? (
                  <span className="absolute right-1 top-1 inline-flex items-center gap-0.5 rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                    <Flame className="h-2.5 w-2.5" aria-hidden />#{topRank.get(i) + 1}
                  </span>
                ) : null}
                {f.faces?.length ? (
                  <span className="absolute left-1 top-1 inline-flex items-center gap-0.5 rounded bg-white/90 px-1 py-0.5 text-[10px] font-medium text-slate-700">
                    <ScanFace className="h-2.5 w-2.5" aria-hidden />{f.faces.length}
                  </span>
                ) : null}
              </div>
              <div className="px-2 py-1.5">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-slate-500">#{i + 1}</span>
                  <span className="font-semibold tabular-nums" style={{ color: suspicionColor(s) }}>{s == null ? 'n/a' : pct(s)}</span>
                </div>
                <div className="mt-1 h-1 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full" style={{ width: `${(s ?? 0) * 100}%`, background: suspicionColor(s) }} />
                </div>
              </div>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

/* -------------------------------------------------------- selected frame */

function SelectedFrame({ frame, index, total, width, height, onPrev, onNext, isTop }) {
  const [tab, setTab] = useState('frame')
  const [showFaces, setShowFaces] = useState(true)
  const hasHeat = Boolean(frame?.heatmap_url)
  const view = tab === 'heatmap' && !hasHeat ? 'frame' : tab
  const faces = frame?.faces || []
  const thumb = withToken(frame?.thumbnail_url)

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-3 py-2">
        <div className="flex items-center gap-1">
          <button onClick={onPrev} disabled={index <= 0} className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 disabled:opacity-30" aria-label="Previous frame">
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="min-w-0 px-1 text-sm font-semibold text-slate-900">
            Frame {index + 1}<span className="font-normal text-slate-400">/{total}</span>
            <span className="ml-2 font-mono text-xs font-normal text-slate-500">{formatTimestamp(frame?.timestamp_s)}</span>
          </span>
          <button onClick={onNext} disabled={index >= total - 1} className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 disabled:opacity-30" aria-label="Next frame">
            <ChevronRight className="h-4 w-4" />
          </button>
          {isTop ? (
            <span className="ml-1 inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-700 ring-1 ring-inset ring-red-600/20">
              <Flame className="h-3 w-3" aria-hidden /> Most suspicious
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-1">
          <div className="flex gap-1 rounded-lg bg-slate-100 p-1" role="tablist" aria-label="Frame views">
            {[
              { key: 'frame', label: 'Frame' },
              { key: 'heatmap', label: 'Heatmap', disabled: !hasHeat },
            ].map((t) => (
              <button
                key={t.key}
                role="tab"
                aria-selected={view === t.key}
                disabled={t.disabled}
                onClick={() => setTab(t.key)}
                title={t.disabled ? 'No heatmap for this frame' : undefined}
                className={`rounded-md px-3 py-1 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-40 ${
                  view === t.key ? 'bg-white text-navy-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          {view === 'frame' ? (
            <button
              onClick={() => setShowFaces((v) => !v)}
              aria-pressed={showFaces}
              className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium ring-1 ring-inset transition ${
                showFaces ? 'bg-cyan-50 text-cyan-700 ring-cyan-200' : 'text-slate-500 ring-slate-200'
              }`}
            >
              <ScanFace className="h-3.5 w-3.5" aria-hidden /> Faces ({faces.length})
            </button>
          ) : null}
        </div>
      </div>
      <div className="checker flex min-h-[240px] items-center justify-center p-2 sm:p-4" role="tabpanel">
        {!thumb ? (
          <div className="flex flex-col items-center gap-2 text-slate-400">
            <ImageOff className="h-8 w-8" aria-hidden />
            <span className="text-sm">Frame thumbnail not available</span>
          </div>
        ) : view === 'heatmap' ? (
          <CompareSlider before={thumb} after={withToken(frame.heatmap_url)} beforeLabel="Frame" afterLabel="Heatmap" alt={`frame ${index + 1}`} />
        ) : (
          <div className="relative inline-block max-w-full">
            <img src={thumb} alt={`Frame ${index + 1} at ${formatTimestamp(frame.timestamp_s)}`} className="block max-h-[460px] w-auto max-w-full object-contain" draggable={false} />
            <BoxOverlay width={width} height={height} faces={faces} showFaces={showFaces} showRegions={false} />
          </div>
        )}
      </div>
    </div>
  )
}

function FramePanel({ frame }) {
  const faces = frame?.faces || []
  const rows = [
    { label: 'Fused suspicion', value: frame?.suspicion },
    { label: 'Face deepfake', value: frame?.deepfake_probability, empty: faces.length ? 'Not checked' : 'No face' },
    { label: 'AI-generated', value: frame?.ai_generated_probability, empty: 'Not checked' },
  ]
  return (
    <div className="card p-5">
      <h2 className="section-title flex items-center gap-2"><Activity className="h-5 w-5 text-cyan-600" aria-hidden /> Frame scores</h2>
      <ul className="mt-4 space-y-3">
        {rows.map((r) => (
          <li key={r.label}>
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-600">{r.label}</span>
              {r.value == null ? (
                <span className="text-xs font-medium text-slate-400">{r.empty || 'n/a'}</span>
              ) : (
                <span className="font-semibold tabular-nums" style={{ color: suspicionColor(r.value) }}>{pct(r.value)}</span>
              )}
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
              {r.value != null ? <div className="h-full rounded-full" style={{ width: `${r.value * 100}%`, background: suspicionColor(r.value) }} /> : null}
            </div>
          </li>
        ))}
      </ul>

      <h3 className="mt-6 flex items-center gap-2 text-sm font-semibold text-slate-900"><ScanFace className="h-4 w-4 text-cyan-600" aria-hidden /> Faces in this frame</h3>
      {faces.length ? (
        <ul className="mt-3 space-y-2">
          {faces.map((f, i) => {
            const checked = f.deepfake_probability != null
            const p = Math.max(0, Math.min(1, f.deepfake_probability ?? 0))
            const color = checked ? suspicionColor(p) : '#94a3b8'
            return (
              <li key={i} className="rounded-xl bg-slate-50 px-3.5 py-2.5">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium text-slate-800">Face {i + 1}</span>
                  <span className={`tabular-nums ${checked ? 'font-serif text-base font-bold' : 'text-xs font-medium'}`} style={{ color }}>
                    {checked ? pct(p) : 'Not checked'}
                  </span>
                </div>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-200">
                  {checked ? <div className="h-full rounded-full" style={{ width: `${p * 100}%`, background: color }} /> : null}
                </div>
                <p className="mt-1 text-[11px] text-slate-500">Deepfake probability · box [{(f.box || []).join(', ')}]</p>
              </li>
            )
          })}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-slate-500">No faces were detected in this frame.</p>
      )}
    </div>
  )
}

/* -------------------------------------------------------------- metadata */

function fmt(v) {
  if (v == null || v === '') return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

function VideoMetadata({ info, metadata, video }) {
  const [open, setOpen] = useState(false)
  const tags = Object.entries(metadata?.tags || {})
  const hint = metadata?.generator_hint
  const basics = [
    ['Format', info.format],
    ['Codec', info.codec],
    ['Encoder', metadata?.encoder],
    ['Duration', info.duration_s != null ? formatDuration(info.duration_s) : null],
    ['Resolution', info.width ? `${info.width} × ${info.height}px` : null],
    ['Frame rate', formatFps(info.fps)],
    ['Frames', info.frame_count],
    ['File size', video?.size_bytes != null ? formatBytes(video.size_bytes) : null],
  ]
  return (
    <div className="card">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between gap-3 rounded-xl px-5 py-4 text-left" aria-expanded={open}>
        <span className="flex items-center gap-2">
          <FileSearch className="h-5 w-5 text-cyan-600" aria-hidden />
          <span className="section-title">Video metadata</span>
        </span>
        <span className="flex items-center gap-2 text-xs text-slate-500">
          {tags.length} container tag{tags.length === 1 ? '' : 's'}
          <ChevronDown className={`h-5 w-5 text-slate-400 transition ${open ? 'rotate-180' : ''}`} aria-hidden />
        </span>
      </button>
      {hint ? (
        <div className="mx-5 mb-3 flex items-start gap-2.5 rounded-xl border-l-4 border-amber-400 bg-amber-50 px-3.5 py-3" role="note">
          <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden />
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-amber-800">Generator hint</p>
            <p className="mt-0.5 text-sm text-amber-900">
              The file's metadata references <span className="font-semibold">{hint}</span>, a known AI video generator.
            </p>
          </div>
        </div>
      ) : null}
      <div className="grid grid-cols-2 gap-3 px-5 pb-4 sm:grid-cols-4">
        {basics.map(([k, v]) => (
          <div key={k} className="min-w-0 rounded-xl bg-slate-50 px-3 py-2">
            <p className="text-[11px] uppercase tracking-wide text-slate-400">{k}</p>
            <p className={`truncate text-sm font-medium ${k === 'Encoder' && hint ? 'text-amber-700' : 'text-slate-800'}`} title={fmt(v)}>{fmt(v)}</p>
          </div>
        ))}
      </div>
      {open ? (
        <div className="border-t border-slate-100 px-5 py-4">
          {tags.length ? (
            <div className="max-h-80 overflow-auto rounded-xl ring-1 ring-slate-200">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                  <tr><th className="px-3 py-2 font-semibold">Tag</th><th className="px-3 py-2 font-semibold">Value</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {tags.map(([k, v]) => (
                    <tr key={k}>
                      <td className="whitespace-nowrap px-3 py-2 font-medium text-slate-700">{k}</td>
                      <td className="break-all px-3 py-2 font-mono text-xs text-slate-600">{fmt(v)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-slate-500">No container tags found. Re-encoded or social-media videos often have their metadata stripped.</p>
          )}
        </div>
      ) : null}
    </div>
  )
}

/* ------------------------------------------------------------------ page */

export default function VideoResult() {
  const { id } = useParams()
  const [analysis, setAnalysis] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)
  const [playhead, setPlayhead] = useState(0)
  const [unsupported, setUnsupported] = useState(false)
  const videoRef = useRef(null)
  const lastTick = useRef(0)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    videoAnalysesApi
      .get(id)
      .then((a) => {
        setAnalysis(a)
        setSelected(a?.result?.top_frames?.[0] ?? 0)
        setUnsupported(false)
      })
      .catch((e) => setError({ status: e?.response?.status, message: errorMessage(e) }))
      .finally(() => setLoading(false))
  }, [id])

  useEffect(load, [load])

  const onTime = useCallback((t) => {
    // Throttle chart re-renders while playing.
    const now = Date.now()
    if (now - lastTick.current < 200) return
    lastTick.current = now
    setPlayhead(t)
  }, [])

  if (loading && !analysis) return <ResultSkeleton />

  if (error && !analysis) {
    return (
      <div className="card">
        <EmptyState
          icon={AlertTriangle}
          title={error.status === 404 ? 'Video analysis not found' : "Couldn't load this analysis"}
          message={error.status === 404 ? 'It may have been deleted, or it belongs to another account.' : error.message}
          action={
            <div className="flex gap-2">
              <Link to="/history" className="btn-outline">Back to history</Link>
              {error.status !== 404 ? <button className="btn-dark" onClick={load}><RefreshCw className="h-4 w-4" aria-hidden /> Retry</button> : null}
            </div>
          }
        />
      </div>
    )
  }

  const result = analysis.result || {}
  const video = analysis.video || {}
  const info = { ...video, ...(result.video || {}) }
  const verdict = analysis.verdict || result.verdict
  const vm = verdictMeta(verdict)
  const signals = result.signals || []
  const frames = result.frames || []
  const topFrames = (result.top_frames || []).filter((i) => i >= 0 && i < frames.length)
  const score = analysis.authenticity_score ?? result.authenticity_score
  const confidence = analysis.confidence ?? result.confidence
  const facesFrames = result.faces_detected_frames ?? frames.filter((f) => f.faces?.length).length
  const modelVersions = result.model_versions || {}
  const sel = selected != null && selected < frames.length ? selected : 0
  const frame = frames[sel]
  const width = info.width
  const height = info.height

  const selectFrame = (i, seek = true) => {
    setSelected(i)
    const t = frames[i]?.timestamp_s
    const v = videoRef.current
    if (seek && v && t != null && !unsupported) {
      try {
        v.currentTime = t
        v.pause()
      } catch {
        /* not seekable yet */
      }
      setPlayhead(t)
    }
  }

  const metaLine = [
    info.duration_s != null ? formatDuration(info.duration_s) : null,
    info.width ? `${info.width}×${info.height}` : null,
    formatFps(info.fps),
  ].filter(Boolean)

  return (
    <div className="animate-fadeIn">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <Link to="/history" className="mb-2 inline-flex items-center gap-1 rounded text-sm text-slate-500 hover:text-slate-800">
            <ArrowLeft className="h-4 w-4" aria-hidden /> History
          </Link>
          <h1 className="flex min-w-0 items-center gap-2 font-serif text-2xl font-bold text-slate-900 sm:text-3xl" title={video.original_filename}>
            <span className="truncate">{video.original_filename || `Video analysis #${analysis.id}`}</span>
            <span className="inline-flex shrink-0 items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 font-sans text-xs font-semibold text-slate-600">
              <Film className="h-3.5 w-3.5" aria-hidden /> Video
            </span>
          </h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-500">
            <span className="inline-flex items-center gap-1"><Clock className="h-3.5 w-3.5" aria-hidden /> {formatDate(analysis.created_at)}</span>
            <span className="inline-flex items-center gap-1"><Cpu className="h-3.5 w-3.5" aria-hidden /> {formatMs(analysis.processing_ms ?? result.processing_ms)}</span>
            {metaLine.length ? <span>{metaLine.join(' · ')}</span> : null}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <a href={withToken(analysis.report_url)} target="_blank" rel="noreferrer" className="btn-primary">
            <Download className="h-4 w-4" aria-hidden /> Download PDF report
          </a>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Verdict panel */}
        <div className="card overflow-hidden">
          <div className="h-1.5" style={{ background: vm.color }} />
          <div className="flex flex-col items-center p-6 text-center">
            <VerdictBadge verdict={verdict} size="lg" />
            <p className="mt-2 text-xs text-slate-500">{VIDEO_BLURBS[verdict] || vm.blurb}</p>
            <div className="mt-5">
              <ScoreGauge score={score} />
            </div>
            <div className="mt-4 grid w-full grid-cols-2 gap-3">
              <div className="rounded-xl bg-slate-50 px-3 py-2.5">
                <p className="text-[11px] uppercase tracking-wide text-slate-400">Confidence</p>
                <p className="font-serif text-xl font-bold text-slate-900">{pct(confidence)}</p>
              </div>
              <div className="rounded-xl bg-slate-50 px-3 py-2.5">
                <p className="text-[11px] uppercase tracking-wide text-slate-400">Frames analysed</p>
                <p className="font-serif text-xl font-bold text-slate-900">{frames.length}</p>
                <p className="text-[11px] text-slate-500">{facesFrames} with faces</p>
              </div>
            </div>
          </div>
          <div className="space-y-3 border-t border-slate-100 p-5">
            {result.summary ? (
              <div className="flex gap-2.5">
                <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-cyan-600" aria-hidden />
                <p className="text-sm leading-relaxed text-slate-700">{result.summary}</p>
              </div>
            ) : null}
            {result.uncertainty_note ? (
              <div className="flex gap-2.5 rounded-xl border-l-4 border-amber-400 bg-amber-50 px-3.5 py-3" role="note">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden />
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-amber-800">Caution</p>
                  <p className="mt-0.5 text-sm leading-relaxed text-amber-900">{result.uncertainty_note}</p>
                </div>
              </div>
            ) : null}
          </div>
        </div>

        {/* Player + timeline */}
        <div className="space-y-6 lg:col-span-2">
          <div className="card overflow-hidden">
            <VideoPlayer
              src={withToken(video.url)}
              mime={(info.format || video.mime_type || '').toUpperCase()}
              videoRef={videoRef}
              onTime={onTime}
              unsupported={unsupported || !video.url}
              onUnsupported={() => setUnsupported(true)}
            />
          </div>
          <div className="card p-5">
            <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
              <div>
                <h2 className="section-title">Suspicion timeline</h2>
                <p className="text-xs text-slate-500">
                  {unsupported ? 'Click a point to inspect that frame.' : 'Click a point to jump the video there and inspect that frame.'} Gaps mean no face or model result.
                </p>
              </div>
            </div>
            {frames.length ? (
              <SuspicionTimeline
                frames={frames}
                duration={info.duration_s}
                selected={sel}
                playhead={unsupported ? null : playhead}
                onSelect={(i) => selectFrame(i)}
              />
            ) : (
              <p className="py-10 text-center text-sm text-slate-500">No frames were sampled for this video.</p>
            )}
          </div>
        </div>
      </div>

      {/* Frame strip */}
      {frames.length ? (
        <section className="mt-8">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
            <div>
              <h2 className="font-serif text-xl font-bold text-slate-900">Sampled frames</h2>
              <p className="text-sm text-slate-500">
                {frames.length} frames sampled evenly across the clip.
                {topFrames.length ? ' Most suspicious frames are marked in red.' : ''}
              </p>
            </div>
            {topFrames.length ? (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-xs font-medium text-slate-500">Most suspicious:</span>
                {topFrames.map((i, r) => (
                  <button
                    key={i}
                    onClick={() => selectFrame(i)}
                    className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset transition ${
                      sel === i ? 'bg-red-600 text-white ring-red-600' : 'bg-red-50 text-red-700 ring-red-600/20 hover:bg-red-100'
                    }`}
                  >
                    #{r + 1} · {formatTimestamp(frames[i]?.timestamp_s)}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          <FrameStrip frames={frames} topFrames={topFrames} selected={sel} onSelect={(i) => selectFrame(i)} />
        </section>
      ) : null}

      {/* Selected frame */}
      {frame ? (
        <section className="mt-8 grid items-start gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <SelectedFrame
              key={sel}
              frame={frame}
              index={sel}
              total={frames.length}
              width={width}
              height={height}
              isTop={topFrames.includes(sel)}
              onPrev={() => selectFrame(Math.max(0, sel - 1))}
              onNext={() => selectFrame(Math.min(frames.length - 1, sel + 1))}
            />
          </div>
          <FramePanel frame={frame} />
        </section>
      ) : null}

      {/* Signals */}
      <section className="mt-8">
        <div className="mb-4">
          <h2 className="font-serif text-xl font-bold text-slate-900">Signal breakdown</h2>
          <p className="text-sm text-slate-500">Each signal reports a suspicion score across the whole clip (higher = more suspicious) and its weight in the fused verdict.</p>
        </div>
        {signals.length ? (
          <div className="grid gap-4 sm:grid-cols-2">
            {signals.map((s) => <SignalCard key={s.key} signal={s} />)}
          </div>
        ) : (
          <div className="card p-6 text-sm text-slate-500">No signal data was returned for this analysis.</div>
        )}
      </section>

      <section className="mt-8 space-y-6">
        <VideoMetadata info={info} metadata={result.metadata} video={video} />
        {(modelVersions.deepfake || modelVersions.ai_generated) ? (
          <p className="flex flex-wrap items-center gap-x-4 gap-y-1 px-1 text-xs text-slate-500">
            <Info className="h-3.5 w-3.5" aria-hidden />
            {modelVersions.deepfake ? <span>Deepfake model: <span className="font-mono text-slate-700">{modelVersions.deepfake}</span></span> : null}
            {modelVersions.ai_generated ? <span>AI-generated model: <span className="font-mono text-slate-700">{modelVersions.ai_generated}</span></span> : null}
          </p>
        ) : null}
      </section>

      <section className="mt-8">
        <div className="flex flex-col items-start justify-between gap-4 rounded-xl border border-slate-200 bg-white p-6 shadow-card sm:flex-row sm:items-center">
          <div className="flex items-start gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-cyan-50 text-cyan-600 ring-1 ring-inset ring-cyan-100"><FileText className="h-5 w-5" aria-hidden /></span>
            <div>
              <h2 className="section-title">Video forensic PDF report</h2>
              <p className="text-sm text-slate-500">Verdict, timeline, most suspicious frames, signals and metadata in one shareable document.</p>
            </div>
          </div>
          <a href={withToken(analysis.report_url)} target="_blank" rel="noreferrer" className="btn-primary">
            <Download className="h-4 w-4" aria-hidden /> Download PDF
          </a>
        </div>
      </section>

      <div className="mt-8"><Disclaimer /></div>
    </div>
  )
}
