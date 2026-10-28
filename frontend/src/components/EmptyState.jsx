export default function EmptyState({ icon: Icon, title, message, action }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      {Icon ? (
        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-400/15 to-violet-500/15 text-cyan-600 ring-1 ring-cyan-500/20">
          <Icon className="h-7 w-7" aria-hidden />
        </div>
      ) : null}
      <h3 className="font-serif text-lg font-semibold text-slate-900">{title}</h3>
      {message ? <p className="mt-1 max-w-sm text-sm text-slate-500">{message}</p> : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  )
}
