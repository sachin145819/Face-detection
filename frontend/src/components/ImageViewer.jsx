import { useState } from 'react'
import { ImageOff, Square, ScanFace } from 'lucide-react'
import CompareSlider from './CompareSlider.jsx'
import BoxOverlay from './BoxOverlay.jsx'

function Img({ src, alt, onLoad }) {
  const [err, setErr] = useState(false)
  if (!src || err) {
    return (
      <div className="flex h-72 w-full flex-col items-center justify-center gap-2 text-slate-400">
        <ImageOff className="h-8 w-8" aria-hidden />
        <span className="text-sm">{src ? 'Image could not be loaded' : 'Not available for this analysis'}</span>
      </div>
    )
  }
  return <img src={src} alt={alt} onLoad={onLoad} onError={() => setErr(true)} className="block max-h-[560px] w-auto max-w-full object-contain" />
}

export default function ImageViewer({ originalUrl, heatmapUrl, elaUrl, width, height, regions = [], faces = [], filename }) {
  const [tab, setTab] = useState('original')
  const [showRegions, setShowRegions] = useState(true)
  const [showFaces, setShowFaces] = useState(true)
  const [natural, setNatural] = useState(null)

  const w = width || natural?.w
  const h = height || natural?.h

  const tabs = [
    { key: 'original', label: 'Original' },
    { key: 'heatmap', label: 'Heatmap', disabled: !heatmapUrl },
    { key: 'ela', label: 'ELA', disabled: !elaUrl },
    { key: 'compare', label: 'Compare', disabled: !heatmapUrl },
  ]

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-3 py-2">
        <div className="flex gap-1 rounded-xl bg-slate-100 p-1" role="tablist" aria-label="Image views">
          {tabs.map((t) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              disabled={t.disabled}
              onClick={() => setTab(t.key)}
              title={t.disabled ? 'Not available for this analysis' : undefined}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-40 sm:text-sm ${
                tab === t.key ? 'bg-white text-navy-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        {tab === 'original' ? (
          <div className="flex gap-1">
            <button
              onClick={() => setShowRegions((v) => !v)}
              aria-pressed={showRegions}
              className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium ring-1 ring-inset transition ${
                showRegions ? 'bg-amber-50 text-amber-700 ring-amber-200' : 'text-slate-500 ring-slate-200'
              }`}
            >
              <Square className="h-3.5 w-3.5" aria-hidden /> Regions ({regions.length})
            </button>
            <button
              onClick={() => setShowFaces((v) => !v)}
              aria-pressed={showFaces}
              className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium ring-1 ring-inset transition ${
                showFaces ? 'bg-cyan-50 text-cyan-700 ring-cyan-200' : 'text-slate-500 ring-slate-200'
              }`}
            >
              <ScanFace className="h-3.5 w-3.5" aria-hidden /> Faces ({faces.length})
            </button>
          </div>
        ) : null}
      </div>
      <div className="checker flex min-h-[300px] items-center justify-center p-2 sm:p-4" role="tabpanel">
        {tab === 'original' ? (
          <div className="relative inline-block max-w-full">
            <Img src={originalUrl} alt={filename || 'Original image'} onLoad={(e) => setNatural({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })} />
            <BoxOverlay width={w} height={h} regions={regions} faces={faces} showRegions={showRegions} showFaces={showFaces} />
          </div>
        ) : null}
        {tab === 'heatmap' ? <Img src={heatmapUrl} alt="Explainability heatmap" /> : null}
        {tab === 'ela' ? <Img src={elaUrl} alt="Error level analysis map" /> : null}
        {tab === 'compare' ? <CompareSlider before={originalUrl} after={heatmapUrl} beforeLabel="Original" afterLabel="Heatmap" /> : null}
      </div>
      <div className="border-t border-slate-100 px-4 py-2 text-xs text-slate-500">
        {tab === 'original' && 'Boxes mark suspicious regions (solid) and detected faces (dashed). Coordinates are mapped from original pixels.'}
        {tab === 'heatmap' && 'Warmer colours indicate areas that contributed most to the verdict.'}
        {tab === 'ela' && 'Error Level Analysis: regions recompressed differently from their surroundings appear brighter.'}
        {tab === 'compare' && 'Drag the handle (or use arrow keys) to compare the original with the heatmap.'}
      </div>
    </div>
  )
}
