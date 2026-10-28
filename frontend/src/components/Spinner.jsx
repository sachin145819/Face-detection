import { Loader2 } from 'lucide-react'

export default function Spinner({ className = 'h-5 w-5', label }) {
  return (
    <span className="inline-flex items-center gap-2">
      <Loader2 className={`animate-spin ${className}`} aria-hidden />
      {label ? <span>{label}</span> : <span className="sr-only">Loading</span>}
    </span>
  )
}

export function FullPageSpinner() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 text-cyan-600">
      <Spinner className="h-8 w-8" />
    </div>
  )
}
