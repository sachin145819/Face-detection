import { useState } from 'react'
import { ChevronDown, FileSearch } from 'lucide-react'

function fmt(v) {
  if (v == null || v === '') return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

export default function MetadataTable({ metadata = {}, image }) {
  const [open, setOpen] = useState(false)
  const exif = metadata?.exif || {}
  const exifEntries = Object.entries(exif)
  const basics = [
    ['Format', metadata?.format],
    ['Dimensions', metadata?.width && metadata?.height ? `${metadata.width} × ${metadata.height}px` : image?.width ? `${image.width} × ${image.height}px` : null],
    ['Software', metadata?.software],
    ['EXIF tags', exifEntries.length],
  ]
  return (
    <div className="card">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 rounded-2xl px-5 py-4 text-left"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2">
          <FileSearch className="h-5 w-5 text-cyan-600" aria-hidden />
          <span className="section-title">Metadata &amp; EXIF</span>
        </span>
        <ChevronDown className={`h-5 w-5 text-slate-400 transition ${open ? 'rotate-180' : ''}`} aria-hidden />
      </button>
      <div className="grid grid-cols-2 gap-3 px-5 pb-4 sm:grid-cols-4">
        {basics.map(([k, v]) => (
          <div key={k} className="rounded-xl bg-slate-50 px-3 py-2">
            <p className="text-[11px] uppercase tracking-wide text-slate-400">{k}</p>
            <p className={`truncate text-sm font-medium ${k === 'Software' && v ? 'text-amber-700' : 'text-slate-800'}`} title={fmt(v)}>{fmt(v)}</p>
          </div>
        ))}
      </div>
      {open ? (
        <div className="border-t border-slate-100 px-5 py-4">
          {exifEntries.length ? (
            <div className="max-h-80 overflow-auto rounded-xl ring-1 ring-slate-200">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-3 py-2 font-semibold">Tag</th>
                    <th className="px-3 py-2 font-semibold">Value</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {exifEntries.map(([k, v]) => (
                    <tr key={k}>
                      <td className="whitespace-nowrap px-3 py-2 font-medium text-slate-700">{k}</td>
                      <td className="break-all px-3 py-2 font-mono text-xs text-slate-600">{fmt(v)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-slate-500">
              No EXIF metadata found. Missing metadata is common for screenshots, social-media downloads and AI-generated images.
            </p>
          )}
        </div>
      ) : null}
    </div>
  )
}
