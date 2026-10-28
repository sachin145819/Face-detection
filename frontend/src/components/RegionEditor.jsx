import { useCallback, useEffect, useRef, useState } from 'react'
import { Square, Paintbrush, Undo2, Trash2, Eraser } from 'lucide-react'

/**
 * Lets the user mark regions on the image, either as rectangles or a painted mask.
 * Everything is stored in ORIGINAL image pixels (width x height), independent of display size.
 * Calls onChange({ boxes: [[x,y,w,h]], hasMask, getMask: () => dataURL|null }).
 */
export default function RegionEditor({ src, width, height, onChange }) {
  const [mode, setMode] = useState('rect')
  const [boxes, setBoxes] = useState([])
  const [draft, setDraft] = useState(null)
  const [brush, setBrush] = useState(24) // in display px
  const [hasMask, setHasMask] = useState(false)
  const [natural, setNatural] = useState(null)
  const wrapRef = useRef(null)
  const canvasRef = useRef(null)
  const drawing = useRef(false)
  const start = useRef(null)
  const last = useRef(null)
  const strokes = useRef([]) // snapshots for undo

  const W = width || natural?.w || 0
  const H = height || natural?.h || 0

  const toImage = useCallback(
    (e) => {
      const r = wrapRef.current.getBoundingClientRect()
      const x = ((e.clientX - r.left) / r.width) * W
      const y = ((e.clientY - r.top) / r.height) * H
      return { x: Math.max(0, Math.min(W, x)), y: Math.max(0, Math.min(H, y)), scale: W / r.width }
    },
    [W, H],
  )

  const getMask = useCallback(() => {
    const c = canvasRef.current
    if (!c || !hasMask) return null
    const tmp = document.createElement('canvas')
    tmp.width = c.width
    tmp.height = c.height
    const t = tmp.getContext('2d')
    t.drawImage(c, 0, 0)
    t.globalCompositeOperation = 'source-in'
    t.fillStyle = '#ffffff'
    t.fillRect(0, 0, tmp.width, tmp.height)
    const out = document.createElement('canvas')
    out.width = c.width
    out.height = c.height
    const o = out.getContext('2d')
    o.fillStyle = '#000000'
    o.fillRect(0, 0, out.width, out.height)
    o.drawImage(tmp, 0, 0)
    return out.toDataURL('image/png')
  }, [hasMask])

  useEffect(() => {
    onChange?.({ boxes, hasMask, getMask })
  }, [boxes, hasMask, getMask, onChange])

  const paint = (from, to, scale) => {
    const ctx = canvasRef.current.getContext('2d')
    ctx.strokeStyle = '#ef4444'
    ctx.fillStyle = '#ef4444'
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.lineWidth = brush * scale
    ctx.globalCompositeOperation = mode === 'erase' ? 'destination-out' : 'source-over'
    ctx.beginPath()
    ctx.moveTo(from.x, from.y)
    ctx.lineTo(to.x, to.y)
    ctx.stroke()
  }

  const onDown = (e) => {
    if (!W || !H) return
    e.preventDefault()
    e.currentTarget.setPointerCapture?.(e.pointerId)
    drawing.current = true
    const p = toImage(e)
    start.current = p
    last.current = p
    if (mode === 'rect') {
      setDraft({ x: p.x, y: p.y, w: 0, h: 0 })
    } else {
      const c = canvasRef.current
      strokes.current.push(c.getContext('2d').getImageData(0, 0, c.width, c.height))
      if (strokes.current.length > 20) strokes.current.shift()
      paint(p, { x: p.x + 0.01, y: p.y + 0.01 }, p.scale)
      if (mode === 'brush') setHasMask(true)
    }
  }

  const onMove = (e) => {
    if (!drawing.current) return
    const p = toImage(e)
    if (mode === 'rect') {
      const s = start.current
      setDraft({ x: Math.min(s.x, p.x), y: Math.min(s.y, p.y), w: Math.abs(p.x - s.x), h: Math.abs(p.y - s.y) })
    } else {
      paint(last.current, p, p.scale)
      last.current = p
    }
  }

  const onUp = () => {
    if (!drawing.current) return
    drawing.current = false
    if (mode === 'rect' && draft) {
      if (draft.w > 4 && draft.h > 4) {
        setBoxes((b) => [...b, [Math.round(draft.x), Math.round(draft.y), Math.round(draft.w), Math.round(draft.h)]])
      }
      setDraft(null)
    }
    if (mode === 'erase') {
      // recompute whether anything is still painted
      const c = canvasRef.current
      const data = c.getContext('2d').getImageData(0, 0, c.width, c.height).data
      let any = false
      for (let i = 3; i < data.length; i += 64) if (data[i]) { any = true; break }
      setHasMask(any)
    }
  }

  const undo = () => {
    if (mode === 'rect') {
      setBoxes((b) => b.slice(0, -1))
    } else {
      const snap = strokes.current.pop()
      if (snap) canvasRef.current.getContext('2d').putImageData(snap, 0, 0)
      if (!strokes.current.length) setHasMask(false)
    }
  }

  const clearAll = () => {
    setBoxes([])
    const c = canvasRef.current
    if (c) c.getContext('2d').clearRect(0, 0, c.width, c.height)
    strokes.current = []
    setHasMask(false)
  }

  const stroke = Math.max(2, Math.round(Math.max(W, H) / 300))
  const tools = [
    { key: 'rect', label: 'Rectangle', icon: Square },
    { key: 'brush', label: 'Brush', icon: Paintbrush },
    { key: 'erase', label: 'Eraser', icon: Eraser },
  ]

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex gap-1 rounded-xl bg-slate-100 p-1" role="radiogroup" aria-label="Marking tool">
          {tools.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              role="radio"
              aria-checked={mode === key}
              onClick={() => setMode(key)}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${mode === key ? 'bg-white text-navy-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}
            >
              <Icon className="h-3.5 w-3.5" aria-hidden /> {label}
            </button>
          ))}
        </div>
        {mode !== 'rect' ? (
          <label className="flex items-center gap-2 text-xs text-slate-600">
            Size
            <input type="range" min={6} max={80} value={brush} onChange={(e) => setBrush(Number(e.target.value))} className="w-24 accent-cyan-500" aria-label="Brush size" />
          </label>
        ) : null}
        <div className="ml-auto flex gap-1">
          <button className="btn-ghost px-2.5 py-1.5 text-xs" onClick={undo} aria-label="Undo">
            <Undo2 className="h-3.5 w-3.5" aria-hidden /> Undo
          </button>
          <button className="btn-ghost px-2.5 py-1.5 text-xs text-red-600 hover:bg-red-50" onClick={clearAll} aria-label="Clear all marks">
            <Trash2 className="h-3.5 w-3.5" aria-hidden /> Clear
          </button>
        </div>
      </div>
      <div className="checker flex justify-center rounded-xl p-2">
        <div
          ref={wrapRef}
          className={`relative inline-block max-w-full touch-none select-none ${mode === 'rect' ? 'cursor-crosshair' : 'cursor-cell'}`}
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerUp={onUp}
          onPointerCancel={onUp}
        >
          <img
            src={src}
            alt="Image to mark for restoration"
            draggable={false}
            onLoad={(e) => setNatural({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
            className="block max-h-[480px] w-auto max-w-full object-contain"
          />
          {W && H ? (
            <>
              <canvas ref={canvasRef} width={W} height={H} className="pointer-events-none absolute inset-0 h-full w-full opacity-50" />
              <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden>
                {boxes.map(([x, y, w, h], i) => (
                  <g key={i}>
                    <rect x={x} y={y} width={w} height={h} fill="#22d3ee" fillOpacity={0.18} stroke="#22d3ee" strokeWidth={stroke} />
                    <text x={x + stroke * 2} y={y + stroke * 9} fontSize={stroke * 7} fill="#22d3ee" fontWeight="700" fontFamily="Inter">{i + 1}</text>
                  </g>
                ))}
                {draft ? <rect x={draft.x} y={draft.y} width={draft.w} height={draft.h} fill="#22d3ee" fillOpacity={0.12} stroke="#22d3ee" strokeWidth={stroke} strokeDasharray={`${stroke * 3} ${stroke * 2}`} /> : null}
              </svg>
            </>
          ) : null}
        </div>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        {mode === 'rect' ? 'Click and drag to draw boxes around areas to reconstruct.' : mode === 'brush' ? 'Paint over the areas to reconstruct.' : 'Erase painted areas.'}{' '}
        {boxes.length} box{boxes.length === 1 ? '' : 'es'}{hasMask ? ' · mask painted' : ''}.
      </p>
    </div>
  )
}
