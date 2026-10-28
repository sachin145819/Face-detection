import { useRef, useState } from 'react'
import { UploadCloud, ImagePlus } from 'lucide-react'

export const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp']
export const MAX_BYTES = 10 * 1024 * 1024

export function validateFile(file) {
  if (!file) return 'No file selected.'
  if (!ACCEPTED_TYPES.includes(file.type)) return 'Unsupported file type. Please upload a JPEG, PNG or WebP image.'
  if (file.size > MAX_BYTES) return `File is too large (${(file.size / 1024 / 1024).toFixed(1)} MB). Maximum size is 10 MB.`
  return ''
}

export default function UploadZone({
  onFile,
  disabled,
  accept = ACCEPTED_TYPES.join(','),
  noun = 'an image',
  hint = 'JPEG, PNG or WebP · up to 10 MB',
  icon: IdleIcon = UploadCloud,
  dragIcon: DragIcon = ImagePlus,
}) {
  const inputRef = useRef(null)
  const [drag, setDrag] = useState(false)

  const handle = (files) => {
    if (disabled || !files?.length) return
    onFile(files[0])
  }

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label={`Upload ${noun}: drag and drop or press Enter to browse`}
      aria-disabled={disabled}
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(e) => {
        if ((e.key === 'Enter' || e.key === ' ') && !disabled) {
          e.preventDefault()
          inputRef.current?.click()
        }
      }}
      onDragOver={(e) => {
        e.preventDefault()
        if (!disabled) setDrag(true)
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDrag(false)
        handle(e.dataTransfer.files)
      }}
      className={`group relative flex cursor-pointer flex-col items-center justify-center overflow-hidden rounded-2xl border-2 border-dashed px-6 py-14 text-center transition ${
        drag ? 'border-cyan-400 bg-cyan-50' : 'border-slate-300 bg-white hover:border-cyan-400 hover:bg-cyan-50/40'
      } ${disabled ? 'pointer-events-none opacity-60' : ''}`}
    >
      <div className={`flex h-16 w-16 items-center justify-center rounded-xl bg-cyan-50 text-cyan-600 ring-1 ring-inset ring-cyan-100 transition ${drag ? 'scale-110 shadow-glow' : 'group-hover:shadow-glow'}`}>
        {drag ? <DragIcon className="h-8 w-8" aria-hidden /> : <IdleIcon className="h-8 w-8" aria-hidden />}
      </div>
      <p className="mt-5 font-serif text-xl font-semibold text-slate-900">{drag ? 'Drop to upload' : `Drag & drop ${noun} here`}</p>
      <p className="mt-1 text-sm text-slate-500">
        or <span className="font-semibold text-cyan-700 underline-offset-2 group-hover:underline">browse your files</span>
      </p>
      <p className="mt-4 text-xs text-slate-400">{hint}</p>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => {
          handle(e.target.files)
          e.target.value = ''
        }}
      />
    </div>
  )
}
