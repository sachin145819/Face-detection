import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  AlertTriangle, ArrowLeft, Clock, Cpu, Download, FileText, ScanFace, Target, Info, RefreshCw, Lightbulb,
} from 'lucide-react'
import VerdictBadge from '../components/VerdictBadge.jsx'
import ScoreGauge from '../components/ScoreGauge.jsx'
import ImageViewer from '../components/ImageViewer.jsx'
import SignalCard from '../components/SignalCard.jsx'
import MetadataTable from '../components/MetadataTable.jsx'
import RestorationPanel from '../components/RestorationPanel.jsx'
import Disclaimer from '../components/Disclaimer.jsx'
import EmptyState from '../components/EmptyState.jsx'
import { analysesApi } from '../api/index.js'
import { errorMessage } from '../api/client.js'
import { withToken } from '../lib/files.js'
import { formatDate, formatMs, pct } from '../lib/format.js'
import { verdictMeta } from '../lib/verdict.js'

function ResultSkeleton() {
  return (
    <div className="space-y-6">
      <div className="skeleton h-10 w-2/3" />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="skeleton h-[420px]" />
        <div className="skeleton h-[420px] lg:col-span-2" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="skeleton h-36" />)}
      </div>
    </div>
  )
}

function FacesList({ faces }) {
  return (
    <div className="card p-5">
      <h2 className="section-title flex items-center gap-2"><ScanFace className="h-5 w-5 text-cyan-600" aria-hidden /> Detected faces</h2>
      {faces.length ? (
        <ul className="mt-4 space-y-3">
          {faces.map((f, i) => {
            const checked = f.deepfake_probability != null
            const p = Math.max(0, Math.min(1, f.deepfake_probability ?? 0))
            const color = !checked ? '#94a3b8' : p >= 0.66 ? '#dc2626' : p >= 0.33 ? '#f59e0b' : '#16a34a'
            return (
              <li key={i} className="rounded-xl bg-slate-50 px-4 py-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium text-slate-800">Face {i + 1}</span>
                  <span className="font-serif text-lg font-bold tabular-nums" style={{ color }}>{checked ? pct(p) : 'Not checked'}</span>
                </div>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-200">
                  <div className="h-full rounded-full" style={{ width: `${p * 100}%`, background: color }} />
                </div>
                <p className="mt-1.5 text-xs text-slate-500">
                  Deepfake probability · box [{(f.box || []).join(', ')}]
                </p>
              </li>
            )
          })}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-slate-500">No faces were detected, so face-level deepfake analysis did not apply.</p>
      )}
    </div>
  )
}

export default function Result() {
  const { id } = useParams()
  const [analysis, setAnalysis] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    analysesApi
      .get(id)
      .then(setAnalysis)
      .catch((e) => setError({ status: e?.response?.status, message: errorMessage(e) }))
      .finally(() => setLoading(false))
  }, [id])

  useEffect(load, [load])

  if (loading && !analysis) return <ResultSkeleton />

  if (error && !analysis) {
    return (
      <div className="card">
        <EmptyState
          icon={AlertTriangle}
          title={error.status === 404 ? 'Analysis not found' : "Couldn't load this analysis"}
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
  const image = analysis.image || {}
  const verdict = analysis.verdict || result.verdict
  const vm = verdictMeta(verdict)
  const signals = result.signals || []
  const faces = result.faces || []
  const regions = result.regions || []
  const score = analysis.authenticity_score ?? result.authenticity_score
  const confidence = analysis.confidence ?? result.confidence
  const width = image.width || result.metadata?.width
  const height = image.height || result.metadata?.height
  const modelVersions = result.model_versions || {}

  return (
    <div className="animate-fadeIn">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <Link to="/history" className="mb-2 inline-flex items-center gap-1 rounded text-sm text-slate-500 hover:text-slate-800">
            <ArrowLeft className="h-4 w-4" aria-hidden /> History
          </Link>
          <h1 className="truncate font-serif text-2xl font-bold text-slate-900 sm:text-3xl" title={image.original_filename}>
            {image.original_filename || `Analysis #${analysis.id}`}
          </h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-500">
            <span className="inline-flex items-center gap-1"><Clock className="h-3.5 w-3.5" aria-hidden /> {formatDate(analysis.created_at)}</span>
            <span className="inline-flex items-center gap-1"><Cpu className="h-3.5 w-3.5" aria-hidden /> {formatMs(analysis.processing_ms ?? result.processing_ms)}</span>
            {width ? <span>{width}×{height}px</span> : null}
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
            <p className="mt-2 text-xs text-slate-500">{vm.blurb}</p>
            <div className="mt-5">
              <ScoreGauge score={score} />
            </div>
            <div className="mt-4 grid w-full grid-cols-2 gap-3">
              <div className="rounded-xl bg-slate-50 px-3 py-2.5">
                <p className="text-[11px] uppercase tracking-wide text-slate-400">Confidence</p>
                <p className="font-serif text-xl font-bold text-slate-900">{pct(confidence)}</p>
              </div>
              <div className="rounded-xl bg-slate-50 px-3 py-2.5">
                <p className="text-[11px] uppercase tracking-wide text-slate-400">Regions · Faces</p>
                <p className="font-serif text-xl font-bold text-slate-900">{regions.length} · {faces.length}</p>
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

        {/* Image viewer */}
        <div className="lg:col-span-2">
          <ImageViewer
            originalUrl={withToken(image.url)}
            heatmapUrl={withToken(analysis.heatmap_url)}
            elaUrl={withToken(analysis.ela_url)}
            width={width}
            height={height}
            regions={regions}
            faces={faces}
            filename={image.original_filename}
          />
        </div>
      </div>

      {/* Signals */}
      <section className="mt-8">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="font-serif text-xl font-bold text-slate-900">Signal breakdown</h2>
            <p className="text-sm text-slate-500">Each forensic signal reports a suspicion score (higher = more suspicious) and its weight in the fused verdict.</p>
          </div>
        </div>
        {signals.length ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {signals.map((s) => <SignalCard key={s.key} signal={s} />)}
          </div>
        ) : (
          <div className="card p-6 text-sm text-slate-500">No signal data was returned for this analysis.</div>
        )}
      </section>

      <section className="mt-8 grid items-start gap-6 lg:grid-cols-3">
        <FacesList faces={faces} />
        <div className="space-y-6 lg:col-span-2">
          <MetadataTable metadata={result.metadata} image={image} />
          <div className="card p-5">
            <h2 className="section-title flex items-center gap-2"><Target className="h-5 w-5 text-amber-500" aria-hidden /> Suspicious regions</h2>
            {regions.length ? (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-xs uppercase tracking-wide text-slate-400">
                    <tr><th className="py-2 pr-4">#</th><th className="py-2 pr-4">Source</th><th className="py-2 pr-4">Score</th><th className="py-2">Box (x, y, w, h)</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {regions.map((r, i) => (
                      <tr key={i}>
                        <td className="py-2 pr-4 text-slate-500">{i + 1}</td>
                        <td className="py-2 pr-4"><span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-700">{r.source}</span></td>
                        <td className="py-2 pr-4 font-semibold tabular-nums text-slate-800">{pct(r.score)}</td>
                        <td className="py-2 font-mono text-xs text-slate-600">[{(r.box || []).join(', ')}]</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="mt-3 text-sm text-slate-500">No localised suspicious regions were found.</p>
            )}
            {(modelVersions.deepfake || modelVersions.ai_generated) ? (
              <p className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-100 pt-3 text-xs text-slate-500">
                <Info className="h-3.5 w-3.5" aria-hidden />
                {modelVersions.deepfake ? <span>Deepfake model: <span className="font-mono text-slate-700">{modelVersions.deepfake}</span></span> : null}
                {modelVersions.ai_generated ? <span>AI-generated model: <span className="font-mono text-slate-700">{modelVersions.ai_generated}</span></span> : null}
              </p>
            ) : null}
          </div>
        </div>
      </section>

      <section className="mt-8">
        <RestorationPanel
          key={analysis.id}
          analysis={analysis}
          onRestored={(r) => setAnalysis((a) => ({ ...a, restorations: [...(a.restorations || []), r] }))}
        />
      </section>

      <section className="mt-8">
        <div className="flex flex-col items-start justify-between gap-4 rounded-xl border border-slate-200 bg-white p-6 shadow-card sm:flex-row sm:items-center">
          <div className="flex items-start gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-cyan-50 text-cyan-600 ring-1 ring-inset ring-cyan-100"><FileText className="h-5 w-5" aria-hidden /></span>
            <div>
              <h2 className="section-title">Forensic PDF report</h2>
              <p className="text-sm text-slate-500">Verdict, score, signals, heatmaps and metadata in one shareable document.</p>
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
