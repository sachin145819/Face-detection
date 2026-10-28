import { useEffect, useRef } from 'react'
import { AlertTriangle } from 'lucide-react'
import Spinner from './Spinner.jsx'

export default function ConfirmDialog({ open, title, message, confirmLabel = 'Confirm', danger = true, busy, onConfirm, onCancel }) {
  const cancelRef = useRef(null)
  useEffect(() => {
    if (!open) return
    cancelRef.current?.focus()
    const onKey = (e) => e.key === 'Escape' && !busy && onCancel?.()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, busy, onCancel])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
      <div className="absolute inset-0 bg-navy-950/60 backdrop-blur-sm" onClick={() => !busy && onCancel?.()} />
      <div className="card relative w-full max-w-md animate-fadeIn p-6">
        <div className="flex items-start gap-4">
          <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${danger ? 'bg-red-100 text-red-600' : 'bg-cyan-100 text-cyan-700'}`}>
            <AlertTriangle className="h-5 w-5" aria-hidden />
          </div>
          <div>
            <h2 id="confirm-title" className="text-lg font-semibold text-slate-900">{title}</h2>
            <p className="mt-1 text-sm text-slate-600">{message}</p>
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-3">
          <button ref={cancelRef} className="btn-outline" onClick={onCancel} disabled={busy}>Cancel</button>
          <button className={danger ? 'btn-danger' : 'btn-primary'} onClick={onConfirm} disabled={busy}>
            {busy ? <Spinner className="h-4 w-4" /> : null}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
