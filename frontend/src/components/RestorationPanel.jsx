import { useCallback, useMemo, useState } from 'react'
import { Wand2, PencilRuler, AlertTriangle, Download, X } from 'lucide-react'
import CompareSlider from './CompareSlider.jsx'
import RegionEditor from './RegionEditor.jsx'
import Spinner from './Spinner.jsx'
import { analysesApi } from '../api/index.js'
import { errorMessage } from '../api/client.js'
import { useToast } from '../context/ToastContext.jsx'
import { withToken } from '../lib/files.js'
import { formatDate } from '../lib/format.js'

function ReconstructedLabel() {
  return (
    <div className="flex items-start gap-2 rounded-xl bg-violet-50 px-3.5 py-2.5 text-xs font-medium text-violet-800 ring-1 ring-inset ring-violet-200">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <span><strong className="uppercase tracking-wide">AI-reconstructed — not original evidence.</strong> Use for visualisation only; the original image remains the evidential record.</span>
    </div>
  )
}

export default function RestorationPanel({ analysis, onRestored }) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [marking, setMarking] = useState(false)
  const [marks, setMarks] = useState({ boxes: [], hasMask: false, getMask: () => null })
  const restorations = useMemo(() => analysis.restorations || [], [analysis.restorations])
  const [selectedId, setSelectedId] = useState(restorations[restorations.length - 1]?.id ?? null)

  const result = analysis.result || {}
  const flaggedBoxes = useMemo(() => {
    const r = (result.regions || []).map((x) => x.box).filter(Boolean)
    if (r.length) return r
    return (result.faces || []).filter((f) => (f.deepfake_probability ?? 0) >= 0.5).map((f) => f.box).filter(Boolean)
  }, [result.regions, result.faces])

  const selected = restorations.find((r) => r.id === selectedId) || restorations[restorations.length - 1]
  const original = withToken(analysis.image?.url)
  const onMarksChange = useCallback((m) => setMarks(m), [])

  const restore = async (body) => {
    setBusy(true)
    try {
      const r = await analysesApi.restore(analysis.id, body)
      toast.success('Restoration complete')
      setSelectedId(r.id)
      setMarking(false)
      onRestored?.(r)
    } catch (e) {
      toast.error(errorMessage(e, 'Restoration failed.'))
    } finally {
      setBusy(false)
    }
  }

  const restoreFlagged = () => restore(flaggedBoxes.length ? { boxes: flaggedBoxes } : {})

  const restoreMarked = () => {
    const body = {}
    if (marks.boxes.length) body.boxes = marks.boxes
    const mask = marks.hasMask ? marks.getMask() : null
    if (mask) body.mask_base64 = mask
    if (!body.boxes && !body.mask_base64) {
      toast.error('Mark at least one region first.')
      return
    }
    restore(body)
  }

  return (
    <div className="card">
      <div className="flex flex-col gap-3 border-b border-slate-100 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="section-title flex items-center gap-2"><Wand2 className="h-5 w-5 text-violet-500" aria-hidden /> Intelligent restoration</h2>
          <p className="mt-0.5 text-xs text-slate-500">Reconstruct flagged or hand-marked regions with AI inpainting.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn-violet" onClick={restoreFlagged} disabled={busy || marking}>
            {busy && !marking ? <Spinner className="h-4 w-4" /> : <Wand2 className="h-4 w-4" aria-hidden />}
            Restore flagged regions{flaggedBoxes.length ? ` (${flaggedBoxes.length})` : ''}
          </button>
          <button className={marking ? 'btn-outline' : 'btn-dark'} onClick={() => setMarking((m) => !m)} disabled={busy}>
            {marking ? <X className="h-4 w-4" aria-hidden /> : <PencilRuler className="h-4 w-4" aria-hidden />}
            {marking ? 'Cancel marking' : 'Mark region manually'}
          </button>
        </div>
      </div>

      <div className="space-y-5 p-5">
        {marking ? (
          <div className="rounded-xl border border-cyan-200 bg-cyan-50/40 p-4">
            <RegionEditor src={original} width={analysis.image?.width} height={analysis.image?.height} onChange={onMarksChange} />
            <div className="mt-4 flex justify-end">
              <button className="btn-violet" onClick={restoreMarked} disabled={busy || (!marks.boxes.length && !marks.hasMask)}>
                {busy ? <Spinner className="h-4 w-4" /> : <Wand2 className="h-4 w-4" aria-hidden />} Restore marked regions
              </button>
            </div>
          </div>
        ) : null}

        {busy ? (
          <div className="flex items-center gap-3 rounded-xl bg-violet-50 px-4 py-3 text-sm text-violet-800">
            <Spinner className="h-4 w-4" /> Reconstructing regions… this can take a few seconds.
          </div>
        ) : null}

        {selected ? (
          <div className="space-y-3">
            <ReconstructedLabel />
            <div className="checker flex justify-center rounded-xl p-2">
              <CompareSlider before={original} after={withToken(selected.url)} beforeLabel="Original" afterLabel="AI-reconstructed" />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
              <span>
                Method: <span className="font-mono text-slate-700">{selected.method}</span>
                {selected.note ? ` · ${selected.note}` : ''}
              </span>
              <a href={withToken(selected.url)} target="_blank" rel="noreferrer" className="btn-outline px-3 py-1.5 text-xs">
                <Download className="h-3.5 w-3.5" aria-hidden /> Open restored PNG
              </a>
            </div>
          </div>
        ) : !marking && !busy ? (
          <p className="rounded-xl bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
            No restorations yet. Restore the flagged regions automatically, or mark regions yourself.
          </p>
        ) : null}

        {restorations.length > 0 ? (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Restorations ({restorations.length})</h3>
            <div className="flex gap-3 overflow-x-auto pb-1">
              {restorations.slice().reverse().map((r) => (
                <button
                  key={r.id}
                  onClick={() => setSelectedId(r.id)}
                  className={`w-32 shrink-0 overflow-hidden rounded-xl text-left ring-2 transition ${selected?.id === r.id ? 'ring-violet-500' : 'ring-transparent hover:ring-slate-300'}`}
                  aria-pressed={selected?.id === r.id}
                >
                  <img src={withToken(r.url)} alt={`Restoration ${r.id}`} loading="lazy" className="h-20 w-full bg-slate-100 object-cover" />
                  <div className="bg-slate-50 px-2 py-1.5">
                    <p className="truncate font-mono text-[11px] text-slate-700">{r.method}</p>
                    <p className="text-[10px] text-slate-400">{formatDate(r.created_at)}</p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
