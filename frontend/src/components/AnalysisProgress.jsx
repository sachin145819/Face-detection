import { Check, Cpu, Microscope, Brain, Crosshair, Eye, Loader2, Film, ScanFace, Bot, Activity, FileText } from 'lucide-react'

export const STAGES = [
  { key: 'pre', label: 'Preprocessing', text: 'Normalising image, hashing & reading EXIF', icon: Cpu },
  { key: 'forensics', label: 'Forensics', text: 'Error-level, noise & frequency analysis', icon: Microscope },
  { key: 'detection', label: 'Detection', text: 'Deepfake & AI-generated models', icon: Brain },
  { key: 'localisation', label: 'Localisation', text: 'Finding suspicious regions & faces', icon: Crosshair },
  { key: 'explain', label: 'Explainability', text: 'Building heatmaps & summary', icon: Eye },
]

export const VIDEO_STAGES = [
  { key: 'frames', label: 'Extracting frames', text: 'Probing the container & sampling frames evenly', icon: Film },
  { key: 'faces', label: 'Detecting faces', text: 'Locating faces in every sampled frame', icon: ScanFace },
  { key: 'deepfake', label: 'Deepfake analysis', text: 'Scoring each face for synthetic manipulation', icon: Brain },
  { key: 'ai', label: 'AI-generation check', text: 'Checking frames for generative-model traces', icon: Bot },
  { key: 'temporal', label: 'Temporal analysis', text: 'Comparing consistency across the timeline', icon: Activity },
  { key: 'report', label: 'Building report', text: 'Fusing signals into a verdict & summary', icon: FileText },
]

/** `active` = index of the stage in progress; `uploadPct` shown while uploading (active === -1). */
export default function AnalysisProgress({ active, uploadPct, done, stages = STAGES, uploadLabel = 'Uploading image' }) {
  return (
    <div className="space-y-3" aria-live="polite">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-slate-700">
          {done ? 'Analysis complete' : active < 0 ? `${uploadLabel}… ${uploadPct ?? 0}%` : `${stages[active]?.label}…`}
        </span>
        <span className="tabular-nums text-slate-500">
          {done ? '100%' : `${Math.round(Math.max(0, active) * (100 / stages.length) + (active < 0 ? 0 : 8))}%`}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-violet-500 transition-all duration-700"
          style={{ width: done ? '100%' : `${active < 0 ? (uploadPct || 0) * 0.08 : active * (100 / stages.length) + 8}%` }}
        />
      </div>
      <ol className="mt-4 space-y-2">
        {stages.map((s, i) => {
          const state = done || i < active ? 'done' : i === active ? 'active' : 'todo'
          const Icon = s.icon
          return (
            <li
              key={s.key}
              className={`flex items-center gap-3 rounded-xl px-3 py-2.5 transition ${
                state === 'active' ? 'bg-cyan-50 ring-1 ring-inset ring-cyan-200' : ''
              }`}
            >
              <span
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition ${
                  state === 'done' ? 'bg-green-500 text-white' : state === 'active' ? 'bg-cyan-600 text-white' : 'bg-slate-100 text-slate-400'
                }`}
              >
                {state === 'done' ? <Check className="h-4 w-4" aria-hidden /> : state === 'active' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Icon className="h-4 w-4" aria-hidden />}
              </span>
              <div className="min-w-0">
                <p className={`text-sm font-semibold ${state === 'todo' ? 'text-slate-400' : 'text-slate-800'}`}>{s.label}</p>
                <p className="truncate text-xs text-slate-500">{s.text}</p>
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
