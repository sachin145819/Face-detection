import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Image as ImageIcon, Film } from 'lucide-react'
import PageHeader from '../components/PageHeader.jsx'
import ImageAnalyzer from '../components/ImageAnalyzer.jsx'
import VideoAnalyzer from '../components/VideoAnalyzer.jsx'

const MODES = [
  { key: 'image', label: 'Image', icon: ImageIcon },
  { key: 'video', label: 'Video', icon: Film },
]

const COPY = {
  image: { title: 'Analyze an image', subtitle: 'Upload an image to check it for deepfakes, AI generation and manipulation.' },
  video: { title: 'Analyze a video', subtitle: 'Upload a short clip to check it frame by frame for face deepfakes and AI generation.' },
}

function ModeSwitch({ mode, onChange, disabled }) {
  return (
    <div className="inline-flex rounded-lg bg-slate-100 p-1" role="tablist" aria-label="Media type">
      {MODES.map(({ key, label, icon: Icon }) => {
        const active = mode === key
        return (
          <button
            key={key}
            role="tab"
            aria-selected={active}
            disabled={disabled && !active}
            onClick={() => onChange(key)}
            className={`inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
              active ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            <Icon className={`h-4 w-4 ${active ? 'text-cyan-600' : ''}`} aria-hidden /> {label}
          </button>
        )
      })}
    </div>
  )
}

export default function Analyze() {
  const [params, setParams] = useSearchParams()
  const mode = params.get('type') === 'video' ? 'video' : 'image'
  const [busy, setBusy] = useState(false)

  const setMode = (m) => {
    if (busy || m === mode) return
    const next = new URLSearchParams(params)
    if (m === 'video') next.set('type', 'video')
    else next.delete('type')
    setParams(next, { replace: true })
  }

  return (
    <>
      <PageHeader
        eyebrow="New investigation"
        title={COPY[mode].title}
        subtitle={COPY[mode].subtitle}
        actions={<ModeSwitch mode={mode} onChange={setMode} disabled={busy} />}
      />
      {mode === 'video' ? <VideoAnalyzer key="video" onBusyChange={setBusy} /> : <ImageAnalyzer key="image" onBusyChange={setBusy} />}
    </>
  )
}
