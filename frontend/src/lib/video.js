export const VIDEO_EXTENSIONS = ['mp4', 'mov', 'webm', 'avi', 'mkv']
export const VIDEO_MIME_TYPES = [
  'video/mp4',
  'video/quicktime',
  'video/webm',
  'video/x-msvideo',
  'video/avi',
  'video/msvideo',
  'video/x-matroska',
  'video/mkv',
]
export const VIDEO_ACCEPT = [...VIDEO_MIME_TYPES, ...VIDEO_EXTENSIONS.map((e) => `.${e}`)].join(',')
export const MAX_VIDEO_MB = 100
export const MAX_VIDEO_BYTES = MAX_VIDEO_MB * 1024 * 1024

export function fileExtension(name = '') {
  const m = /\.([a-z0-9]+)$/i.exec(name)
  return m ? m[1].toLowerCase() : ''
}

/** Client-side check before upload. Browsers often report an empty MIME type for AVI/MKV, so the extension also counts. */
export function validateVideo(file) {
  if (!file) return 'No file selected.'
  const ext = fileExtension(file.name)
  const typeOk = VIDEO_MIME_TYPES.includes(file.type) || VIDEO_EXTENSIONS.includes(ext)
  if (!typeOk) {
    return 'Unsupported file type. Please upload an MP4, MOV, WebM, AVI or MKV video.'
  }
  if (file.size > MAX_VIDEO_BYTES) {
    return `File is too large (${(file.size / 1024 / 1024).toFixed(1)} MB). Maximum size is ${MAX_VIDEO_MB} MB.`
  }
  return ''
}

/** 75.4 → "1:15" ; 3725 → "1:02:05" */
export function formatDuration(s) {
  if (s == null || Number.isNaN(Number(s))) return '—'
  const total = Math.max(0, Math.round(Number(s)))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const sec = total % 60
  const mm = h ? String(m).padStart(2, '0') : String(m)
  return `${h ? `${h}:` : ''}${mm}:${String(sec).padStart(2, '0')}`
}

/** Timestamp with tenths for short clips: 3.25 → "0:03.2" */
export function formatTimestamp(s) {
  if (s == null || Number.isNaN(Number(s))) return '—'
  const v = Math.max(0, Number(s))
  const m = Math.floor(v / 60)
  const sec = v - m * 60
  return `${m}:${sec.toFixed(1).padStart(4, '0')}`
}

export function formatFps(fps) {
  if (fps == null || !Number(fps)) return null
  const v = Number(fps)
  return `${Number.isInteger(v) ? v : v.toFixed(2).replace(/0+$/, '').replace(/\.$/, '')} fps`
}

export function suspicionColor(s) {
  if (s == null) return '#94a3b8'
  if (s >= 0.66) return '#dc2626'
  if (s >= 0.33) return '#f59e0b'
  return '#16a34a'
}

export function suspicionLabel(s) {
  if (s == null) return 'n/a'
  return s >= 0.66 ? 'High' : s >= 0.33 ? 'Moderate' : 'Low'
}
