import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ScanSearch, X, FileImage, ShieldCheck, Lock, AlertCircle } from 'lucide-react'
import UploadZone, { validateFile } from './UploadZone.jsx'
import AnalysisProgress, { STAGES } from './AnalysisProgress.jsx'
import Spinner from './Spinner.jsx'
import { analysesApi, imagesApi } from '../api/index.js'
import { errorMessage } from '../api/client.js'
import { useToast } from '../context/ToastContext.jsx'
import { formatBytes } from '../lib/format.js'

const STAGE_MS = 2600

export default function ImageAnalyzer({ onBusyChange }) {
  const navigate = useNavigate()
  const toast = useToast()
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [dims, setDims] = useState(null)
  const [error, setError] = useState('')
  const [phase, setPhase] = useState('idle') // idle | uploading | analyzing | done
  const [uploadPct, setUploadPct] = useState(0)
  const [stage, setStage] = useState(-1)
  const uploadedRef = useRef(null) // {fileKey, image}
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

  // Advance the staged progress animation while the backend works.
  useEffect(() => {
    if (phase !== 'analyzing') return undefined
    setStage(0)
    const id = setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), STAGE_MS)
    return () => clearInterval(id)
  }, [phase])

  const pick = (f) => {
    const msg = validateFile(f)
    if (msg) {
      setError(msg)
      toast.error(msg)
      return
    }
    setError('')
    setDims(null)
    setFile(f)
    uploadedRef.current = null
  }

  const clear = () => {
    setFile(null)
    setPreview(null)
    setDims(null)
    setError('')
    uploadedRef.current = null
  }

  const busy = phase === 'uploading' || phase === 'analyzing' || phase === 'done'
  useEffect(() => {
    onBusyChange?.(busy)
  }, [busy, onBusyChange])

  const run = async () => {
    if (!file || busy) return
    setError('')
    const fileKey = `${file.name}-${file.size}-${file.lastModified}`
    try {
      let image = uploadedRef.current?.fileKey === fileKey ? uploadedRef.current.image : null
      if (!image) {
        setPhase('uploading')
        setStage(-1)
        setUploadPct(0)
        image = await imagesApi.upload(file, (e) => {
          if (e.total) setUploadPct(Math.round((e.loaded / e.total) * 100))
        })
        uploadedRef.current = { fileKey, image }
      }
      setPhase('analyzing')
      const analysis = await analysesApi.create(image.id)
      if (!mounted.current) return
      setPhase('done')
      toast.success('Analysis complete')
      setTimeout(() => mounted.current && navigate(`/analyses/${analysis.id}`), 600)
    } catch (err) {
      if (!mounted.current) return
      const msg = errorMessage(err, 'Analysis failed. Please try again.')
      setError(msg)
      toast.error(msg)
      setPhase('idle')
      setStage(-1)
    }
  }

  return (
    <>
      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-4 lg:col-span-3">
          {!file ? (
            <UploadZone onFile={pick} disabled={busy} />
          ) : (
            <div className="card overflow-hidden">
              <div className="checker relative flex max-h-[520px] min-h-[260px] items-center justify-center overflow-hidden">
                {preview ? (
                  <img
                    src={preview}
                    alt={`Preview of ${file.name}`}
                    className="max-h-[520px] w-auto max-w-full object-contain"
                    onLoad={(e) => setDims({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
                  />
                ) : null}
                {phase === 'analyzing' || phase === 'uploading' ? (
                  <>
                    <div className="absolute inset-0 bg-navy-900/30" aria-hidden />
                    <div className="absolute inset-x-0 top-0 h-1/3 animate-scan bg-gradient-to-b from-transparent via-cyan-400/40 to-transparent" aria-hidden />
                  </>
                ) : null}
                {!busy ? (
                  <button onClick={clear} className="absolute right-3 top-3 rounded-full bg-navy-900/80 p-2 text-white shadow hover:bg-navy-900" aria-label="Remove image">
                    <X className="h-4 w-4" />
                  </button>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 px-4 py-3">
                <FileImage className="h-5 w-5 text-slate-400" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-800">{file.name}</p>
                  <p className="text-xs text-slate-500">
                    {file.type.replace('image/', '').toUpperCase()} · {formatBytes(file.size)}
                    {dims ? ` · ${dims.w}×${dims.h}px` : ''}
                  </p>
                </div>
                {!busy ? <button className="btn-ghost text-xs" onClick={clear}>Choose another</button> : null}
              </div>
            </div>
          )}

          {error ? (
            <div className="flex items-start gap-2 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-inset ring-red-200" role="alert">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {error}
            </div>
          ) : null}
        </div>

        <div className="lg:col-span-2">
          <div className="card p-5 lg:sticky lg:top-8">
            {busy ? (
              <>
                <h2 className="section-title mb-4">Running forensic pipeline</h2>
                <AnalysisProgress active={phase === 'uploading' ? -1 : stage} uploadPct={uploadPct} done={phase === 'done'} />
                <p className="mt-4 text-xs text-slate-500">This usually takes 5–15 seconds. Please keep this tab open.</p>
              </>
            ) : (
              <>
                <h2 className="section-title">Ready to analyze</h2>
                <p className="mt-1 text-sm text-slate-500">TruthLens runs five stages and fuses six+ forensic signals into one explainable verdict.</p>
                <ul className="mt-4 space-y-2">
                  {STAGES.map((s) => {
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
                  <ScanSearch className="h-5 w-5" aria-hidden /> Analyze
                </button>
                {!file ? <p className="mt-2 text-center text-xs text-slate-400">Select an image to begin</p> : null}
                <div className="mt-5 space-y-2 border-t border-slate-100 pt-4 text-xs text-slate-500">
                  <p className="flex items-center gap-2"><Lock className="h-3.5 w-3.5" aria-hidden /> Images are private to your account.</p>
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
    </>
  )
}
