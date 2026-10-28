import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ScanSearch, X, Film, ShieldCheck, Lock, AlertCircle, Clapperboard, FileVideo, RotateCcw } from 'lucide-react'
import UploadZone from './UploadZone.jsx'
import AnalysisProgress, { VIDEO_STAGES } from './AnalysisProgress.jsx'
import Spinner from './Spinner.jsx'
import { videoAnalysesApi, videosApi } from '../api/index.js'
import { errorMessage } from '../api/client.js'
import { useToast } from '../context/ToastContext.jsx'
import { formatBytes } from '../lib/format.js'
import { MAX_VIDEO_MB, VIDEO_ACCEPT, fileExtension, formatDuration, validateVideo } from '../lib/video.js'

// Video analysis usually takes 10–30 s; spread the six stages over ~24 s and hold on the last one.
const STAGE_MS = 4000

function videoError(err, fallback) {
  if (err?.response?.status === 413 && typeof err.response.data?.detail !== 'string') {
    return `File is too large (max ${MAX_VIDEO_MB} MB).`
  }
  return errorMessage(err, fallback)
}

export default function VideoAnalyzer({ onBusyChange }) {
  const navigate = useNavigate()
  const toast = useToast()
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [meta, setMeta] = useState(null) // {duration, w, h}
  const [previewError, setPreviewError] = useState(false)
  const [error, setError] = useState('')
  const [phase, setPhase] = useState('idle') // idle | uploading | analyzing | done
  const [uploadPct, setUploadPct] = useState(0)
  const [stage, setStage] = useState(-1)
  const uploadedRef = useRef(null) // {fileKey, video}
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useEffect(() => {
    if (!file) return undefined
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  useEffect(() => {
    if (phase !== 'analyzing') return undefined
    setStage(0)
    const id = setInterval(() => setStage((s) => Math.min(s + 1, VIDEO_STAGES.length - 1)), STAGE_MS)
    return () => clearInterval(id)
  }, [phase])

  const busy = phase === 'uploading' || phase === 'analyzing' || phase === 'done'
  useEffect(() => {
    onBusyChange?.(busy)
  }, [busy, onBusyChange])

  const pick = (f) => {
    const msg = validateVideo(f)
    if (msg) {
      setError(msg)
      toast.error(msg)
      return
    }
    setError('')
    setMeta(null)
    setPreviewError(false)
    setFile(f)
    uploadedRef.current = null
  }

  const clear = () => {
    setFile(null)
    setPreview(null)
    setMeta(null)
    setPreviewError(false)
    setError('')
    uploadedRef.current = null
  }

  const run = async () => {
    if (!file || busy) return
    setError('')
    const fileKey = `${file.name}-${file.size}-${file.lastModified}`
    try {
      let video = uploadedRef.current?.fileKey === fileKey ? uploadedRef.current.video : null
      if (!video) {
        setPhase('uploading')
        setStage(-1)
        setUploadPct(0)
        video = await videosApi.upload(file, (e) => {
          if (e.total) setUploadPct(Math.round((e.loaded / e.total) * 100))
        })
        uploadedRef.current = { fileKey, video }
      }
      setPhase('analyzing')
      const analysis = await videoAnalysesApi.create(video.id)
      if (!mounted.current) return
      setPhase('done')
      toast.success('Video analysis complete')
      setTimeout(() => mounted.current && navigate(`/video-analyses/${analysis.id}`), 600)
    } catch (err) {
      if (!mounted.current) return
      const msg = videoError(err, 'Video analysis failed. Please try again.')
      setError(msg)
      toast.error(msg)
      setPhase('idle')
      setStage(-1)
    }
  }

  const uploaded = Boolean(file && uploadedRef.current?.fileKey === `${file.name}-${file.size}-${file.lastModified}`)
  const ext = file ? fileExtension(file.name).toUpperCase() || 'VIDEO' : ''

  return (
    <div className="grid gap-6 lg:grid-cols-5">
      <div className="space-y-4 lg:col-span-3">
        {!file ? (
          <UploadZone
            onFile={pick}
            disabled={busy}
            accept={VIDEO_ACCEPT}
            noun="a video"
            hint={`MP4, MOV, WebM, AVI or MKV · up to ${MAX_VIDEO_MB} MB`}
            icon={Film}
            dragIcon={Clapperboard}
          />
        ) : (
          <div className="card overflow-hidden">
            <div className="relative flex max-h-[520px] min-h-[260px] items-center justify-center overflow-hidden bg-navy-900">
              {preview && !previewError ? (
                <video
                  key={preview}
                  src={preview}
                  controls={!busy}
                  muted
                  playsInline
                  preload="metadata"
                  className="max-h-[520px] w-full object-contain"
                  onLoadedMetadata={(e) => {
                    const v = e.currentTarget
                    setMeta({ duration: v.duration, w: v.videoWidth, h: v.videoHeight })
                  }}
                  onError={() => setPreviewError(true)}
                >
                  <track kind="captions" />
                </video>
              ) : (
                <div className="flex flex-col items-center gap-2 px-6 py-16 text-center text-slate-300">
                  <FileVideo className="h-10 w-10 text-slate-400" aria-hidden />
                  <p className="text-sm font-medium text-white">Preview not available in this browser</p>
                  <p className="max-w-xs text-xs text-slate-400">The {ext} codec can't be played here, but TruthLens can still analyse the file.</p>
                </div>
              )}
              {busy ? (
                <>
                  <div className="pointer-events-none absolute inset-0 bg-navy-900/30" aria-hidden />
                  <div className="pointer-events-none absolute inset-x-0 top-0 h-1/3 animate-scan bg-gradient-to-b from-transparent via-cyan-400/40 to-transparent" aria-hidden />
                </>
              ) : (
                <button onClick={clear} className="absolute right-3 top-3 rounded-full bg-navy-900/80 p-2 text-white shadow hover:bg-navy-900" aria-label="Remove video">
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 px-4 py-3">
              <Film className="h-5 w-5 text-slate-400" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-slate-800">{file.name}</p>
                <p className="text-xs text-slate-500">
                  {ext} · {formatBytes(file.size)}
                  {meta?.duration && Number.isFinite(meta.duration) ? ` · ${formatDuration(meta.duration)}` : ''}
                  {meta?.w ? ` · ${meta.w}×${meta.h}px` : ''}
                </p>
              </div>
              {!busy ? <button className="btn-ghost text-xs" onClick={clear}>Choose another</button> : null}
            </div>
            {phase === 'uploading' ? (
              <div className="border-t border-slate-100 px-4 py-3">
                <div className="mb-1.5 flex justify-between text-xs text-slate-500">
                  <span>Uploading…</span>
                  <span className="tabular-nums">{uploadPct}%</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={uploadPct} aria-label="Upload progress">
                  <div className="h-full rounded-full bg-cyan-600 transition-all duration-300" style={{ width: `${uploadPct}%` }} />
                </div>
              </div>
            ) : null}
          </div>
        )}

        {error ? (
          <div className="flex flex-wrap items-start gap-2 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-inset ring-red-200" role="alert">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span className="min-w-0 flex-1">{error}</span>
            {file && !busy ? (
              <button className="inline-flex items-center gap-1 text-xs font-semibold text-red-700 hover:underline" onClick={run}>
                <RotateCcw className="h-3.5 w-3.5" aria-hidden /> Retry
              </button>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="lg:col-span-2">
        <div className="card p-5 lg:sticky lg:top-24">
          {busy ? (
            <>
              <h2 className="section-title mb-4">Analysing video</h2>
              <AnalysisProgress
                active={phase === 'uploading' ? -1 : stage}
                uploadPct={uploadPct}
                done={phase === 'done'}
                stages={VIDEO_STAGES}
                uploadLabel="Uploading video"
              />
              <p className="mt-4 text-xs text-slate-500">Video analysis usually takes 10–30 seconds. Please keep this tab open.</p>
            </>
          ) : (
            <>
              <h2 className="section-title">Ready to analyze</h2>
              <p className="mt-1 text-sm text-slate-500">
                TruthLens samples frames across the clip, checks every face and frame, and plots suspicion over time.
              </p>
              <ul className="mt-4 space-y-2">
                {VIDEO_STAGES.map((s) => {
                  const Icon = s.icon
                  return (
                    <li key={s.key} className="flex items-center gap-3 text-sm text-slate-600">
                      <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-100 text-slate-500"><Icon className="h-3.5 w-3.5" aria-hidden /></span>
                      {s.label}
                    </li>
                  )
                })}
              </ul>
              <button className="btn-primary mt-6 w-full py-3 text-base" onClick={run} disabled={!file}>
                <ScanSearch className="h-5 w-5" aria-hidden /> {uploaded ? 'Retry analysis' : 'Analyze video'}
              </button>
              {!file ? <p className="mt-2 text-center text-xs text-slate-400">Select a video to begin</p> : null}
              {uploaded ? <p className="mt-2 text-center text-xs text-slate-400">Already uploaded — retrying won't upload it again.</p> : null}
              <div className="mt-5 space-y-2 border-t border-slate-100 pt-4 text-xs text-slate-500">
                <p className="flex items-center gap-2"><Lock className="h-3.5 w-3.5" aria-hidden /> Videos are private to your account.</p>
                <p className="flex items-center gap-2"><ShieldCheck className="h-3.5 w-3.5" aria-hidden /> Results are probabilistic evidence, not certainty.</p>
              </div>
            </>
          )}
          {phase === 'done' ? (
            <p className="mt-4 flex items-center gap-2 text-sm text-green-700"><Spinner className="h-4 w-4" /> Opening results…</p>
          ) : null}
        </div>
      </div>
    </div>
  )
}
