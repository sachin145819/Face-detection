/**
 * SVG overlay drawn in ORIGINAL image pixel coordinates (viewBox = original size),
 * so boxes scale automatically to whatever size the image is displayed at.
 */
const SOURCE_COLORS = {
  ela: '#f59e0b',
  noise: '#8b5cf6',
  deepfake: '#ef4444',
  gradcam: '#ec4899',
}

export default function BoxOverlay({ width, height, regions = [], faces = [], showRegions = true, showFaces = true }) {
  if (!width || !height) return null
  const stroke = Math.max(2, Math.round(Math.max(width, height) / 300))
  const font = Math.max(12, Math.round(Math.max(width, height) / 55))
  return (
    <svg
      className="pointer-events-none absolute inset-0 h-full w-full"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden
    >
      {showRegions &&
        regions.map((r, i) => {
          const [x, y, w, h] = r.box || []
          if (w == null) return null
          const c = SOURCE_COLORS[r.source] || '#f59e0b'
          return (
            <g key={`r${i}`}>
              <rect x={x} y={y} width={w} height={h} fill={c} fillOpacity={0.12} stroke={c} strokeWidth={stroke} rx={stroke} />
              <rect x={x} y={Math.max(0, y - font * 1.4)} width={font * 7} height={font * 1.4} fill={c} rx={stroke} />
              <text x={x + font * 0.35} y={Math.max(0, y - font * 1.4) + font * 1.05} fontSize={font} fill="#fff" fontFamily="Inter, sans-serif" fontWeight="600">
                {r.source} {Math.round((r.score ?? 0) * 100)}%
              </text>
            </g>
          )
        })}
      {showFaces &&
        faces.map((f, i) => {
          const [x, y, w, h] = f.box || []
          if (w == null) return null
          const checked = f.deepfake_probability != null
          const p = f.deepfake_probability ?? 0
          const c = p >= 0.5 ? '#ef4444' : checked ? '#22d3ee' : '#94a3b8'
          return (
            <g key={`f${i}`}>
              <rect x={x} y={y} width={w} height={h} fill="none" stroke={c} strokeWidth={stroke} strokeDasharray={`${stroke * 4} ${stroke * 2.5}`} rx={stroke * 2} />
              <rect x={x} y={y + h} width={font * 7.5} height={font * 1.4} fill={c} rx={stroke} />
              <text x={x + font * 0.35} y={y + h + font * 1.05} fontSize={font} fill="#0b1120" fontFamily="Inter, sans-serif" fontWeight="700">
                Face {i + 1} · {checked ? `${Math.round(p * 100)}%` : 'n/a'}
              </text>
            </g>
          )
        })}
    </svg>
  )
}
