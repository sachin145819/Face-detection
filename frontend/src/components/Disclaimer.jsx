import { Scale } from 'lucide-react'

export default function Disclaimer() {
  return (
    <div className="flex items-center justify-center gap-2 border-t border-slate-200 px-4 py-5 text-center text-xs text-slate-500">
      <Scale className="h-4 w-4 shrink-0 text-slate-400" aria-hidden />
      <span>Probabilistic evidence, corroborated by human review — never a substitute for it.</span>
    </div>
  )
}
