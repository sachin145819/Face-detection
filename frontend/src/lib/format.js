export function formatDate(iso, opts = {}) {
  if (!iso) return '—'
  const d = parseDate(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    ...opts,
  })
}

export function formatShortDate(iso) {
  return formatDate(iso, { hour: undefined, minute: undefined })
}

// Backend datetimes are UTC; treat naive strings as UTC.
export function parseDate(iso) {
  if (typeof iso !== 'string') return new Date(iso)
  const hasTz = /([zZ]|[+-]\d{2}:?\d{2})$/.test(iso)
  return new Date(hasTz ? iso : `${iso}Z`)
}

export function formatBytes(n) {
  if (n == null) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(2)} MB`
}

export function pct(x, digits = 0) {
  if (x == null || Number.isNaN(Number(x))) return '—'
  return `${(Number(x) * 100).toFixed(digits)}%`
}

export function round(x, digits = 0) {
  if (x == null || Number.isNaN(Number(x))) return '—'
  return Number(x).toFixed(digits)
}

export function formatMs(ms) {
  if (ms == null) return '—'
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

export function weekdayLabel(yyyyMmDd) {
  const d = new Date(`${yyyyMmDd}T00:00:00`)
  if (Number.isNaN(d.getTime())) return yyyyMmDd
  return d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' })
}
