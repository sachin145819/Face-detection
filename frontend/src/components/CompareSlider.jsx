import { useCallback, useRef, useState } from 'react'
import { MoveHorizontal } from 'lucide-react'

/**
 * Before/after slider. Both images are rendered with identical sizing; the "after"
 * image is revealed with a clip-path controlled by a draggable handle.
 */
export default function CompareSlider({ before, after, beforeLabel = 'Original', afterLabel = 'Heatmap', alt = '' }) {
  const [pos, setPos] = useState(50)
  const ref = useRef(null)
  const dragging = useRef(false)

  const update = useCallback((clientX) => {
    const r = ref.current?.getBoundingClientRect()
    if (!r || !r.width) return
    setPos(Math.max(0, Math.min(100, ((clientX - r.left) / r.width) * 100)))
  }, [])

  return (
    <div
      ref={ref}
      className="relative inline-block max-w-full touch-none select-none overflow-hidden"
      onPointerDown={(e) => {
        dragging.current = true
        e.currentTarget.setPointerCapture?.(e.pointerId)
        update(e.clientX)
      }}
      onPointerMove={(e) => dragging.current && update(e.clientX)}
      onPointerUp={() => (dragging.current = false)}
      onPointerCancel={() => (dragging.current = false)}
    >
      <img src={before} alt={`${beforeLabel}${alt ? ` — ${alt}` : ''}`} className="block max-h-[560px] w-auto max-w-full object-contain" draggable={false} />
      <img
        src={after}
        alt={`${afterLabel}${alt ? ` — ${alt}` : ''}`}
        className="absolute inset-0 block h-full w-full object-contain"
        style={{ clipPath: `inset(0 0 0 ${pos}%)` }}
        draggable={false}
      />
      <div className="pointer-events-none absolute inset-y-0" style={{ left: `${pos}%` }}>
        <div className="absolute inset-y-0 -ml-px w-0.5 bg-white shadow-[0_0_8px_rgba(0,0,0,0.5)]" />
        <div className="absolute top-1/2 -ml-5 -mt-5 flex h-10 w-10 items-center justify-center rounded-full bg-white text-navy-900 shadow-lg ring-2 ring-cyan-400">
          <MoveHorizontal className="h-5 w-5" aria-hidden />
        </div>
      </div>
      <span className="pointer-events-none absolute left-2 top-2 rounded-md bg-navy-900/80 px-2 py-1 text-[11px] font-semibold text-white">{beforeLabel}</span>
      <span className="pointer-events-none absolute right-2 top-2 rounded-md bg-navy-900/80 px-2 py-1 text-[11px] font-semibold text-cyan-300">{afterLabel}</span>
      <input
        type="range"
        min={0}
        max={100}
        value={Math.round(pos)}
        onChange={(e) => setPos(Number(e.target.value))}
        className="absolute inset-x-0 bottom-0 h-6 w-full cursor-ew-resize opacity-0 focus-visible:opacity-30"
        aria-label={`Compare ${beforeLabel} and ${afterLabel}`}
      />
    </div>
  )
}
