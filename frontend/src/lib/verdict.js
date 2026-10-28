import { ShieldCheck, ScanFace, Bot, Layers } from 'lucide-react'

export const VERDICTS = {
  authentic: {
    label: 'Authentic',
    color: '#16a34a',
    soft: 'bg-green-50 text-green-700 ring-green-600/20',
    solid: 'bg-green-600',
    icon: ShieldCheck,
    blurb: 'No significant evidence of manipulation was found.',
  },
  manipulated: {
    label: 'Manipulated',
    color: '#f59e0b',
    soft: 'bg-amber-50 text-amber-700 ring-amber-600/20',
    solid: 'bg-amber-500',
    icon: Layers,
    blurb: 'Parts of this image appear to have been edited or spliced.',
  },
  deepfake: {
    label: 'Deepfake',
    color: '#dc2626',
    soft: 'bg-red-50 text-red-700 ring-red-600/20',
    solid: 'bg-red-600',
    icon: ScanFace,
    blurb: 'Facial regions show signs of synthetic face manipulation.',
  },
  ai_generated: {
    label: 'AI-generated',
    color: '#8b5cf6',
    soft: 'bg-violet-50 text-violet-700 ring-violet-600/20',
    solid: 'bg-violet-500',
    icon: Bot,
    blurb: 'The image shows characteristics of generative AI models.',
  },
}

export const VERDICT_KEYS = ['authentic', 'manipulated', 'deepfake', 'ai_generated']

export function verdictMeta(v) {
  return (
    VERDICTS[v] || {
      label: v ? String(v) : 'Unknown',
      color: '#64748b',
      soft: 'bg-slate-100 text-slate-700 ring-slate-500/20',
      solid: 'bg-slate-500',
      icon: ShieldCheck,
      blurb: '',
    }
  )
}

export function scoreColor(score) {
  if (score == null) return '#64748b'
  if (score >= 70) return '#16a34a'
  if (score >= 40) return '#f59e0b'
  return '#dc2626'
}
