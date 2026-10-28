import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import { CheckCircle2, AlertTriangle, Info, X } from 'lucide-react'

const ToastContext = createContext(null)

const STYLES = {
  success: { icon: CheckCircle2, cls: 'border-green-500/40', iconCls: 'text-green-400' },
  error: { icon: AlertTriangle, cls: 'border-red-500/40', iconCls: 'text-red-400' },
  info: { icon: Info, cls: 'border-cyan-500/40', iconCls: 'text-cyan-400' },
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const idRef = useRef(0)

  const dismiss = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), [])

  const push = useCallback(
    (type, message, timeout = 4500) => {
      const id = ++idRef.current
      setToasts((t) => [...t.slice(-3), { id, type, message }])
      if (timeout) setTimeout(() => dismiss(id), timeout)
      return id
    },
    [dismiss],
  )

  const api = useMemo(
    () => ({
      success: (m) => push('success', m),
      error: (m) => push('error', m, 6500),
      info: (m) => push('info', m),
      dismiss,
    }),
    [push, dismiss],
  )

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        className="pointer-events-none fixed inset-x-0 bottom-4 z-[100] flex flex-col items-center gap-2 px-4 sm:inset-x-auto sm:right-4 sm:items-end"
        aria-live="polite"
        role="status"
      >
        {toasts.map((t) => {
          const s = STYLES[t.type] || STYLES.info
          const Icon = s.icon
          return (
            <div
              key={t.id}
              className={`pointer-events-auto flex w-full max-w-sm animate-fadeIn items-start gap-3 rounded-xl border bg-navy-900 px-4 py-3 text-sm text-slate-100 shadow-xl ${s.cls}`}
            >
              <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${s.iconCls}`} aria-hidden />
              <p className="flex-1 leading-snug">{t.message}</p>
              <button
                onClick={() => dismiss(t.id)}
                className="rounded p-0.5 text-slate-400 hover:text-white"
                aria-label="Dismiss notification"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>')
  return ctx
}
