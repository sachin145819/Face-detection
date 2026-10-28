import { Link } from 'react-router-dom'
import {
  ShieldCheck, ScanFace, Bot, Flame, Wand2, FileText, Film, Lock,
  Upload, Cpu, Microscope, Brain, Crosshair, Eye, ClipboardCheck, ArrowRight, Check, Minus,
} from 'lucide-react'
import { PublicFooter, PublicNav } from '../components/PublicLayout.jsx'
import { useAuth } from '../context/AuthContext.jsx'

const STATS = [
  { value: '15,736+', label: 'verified deepfake attack victims in H1 2026', source: 'Resemble AI, 2026' },
  { value: '1 in 5', label: 'biometric fraud attempts now involve a deepfake', source: 'Entrust, 2026' },
  { value: '0.1%', label: 'of people reliably tell AI-generated images from real', source: 'iProov, 2025' },
]

const FEATURES = [
  { icon: ShieldCheck, title: 'Authenticity scoring', text: 'A single 0–100 score fused from metadata, compression, noise and deep-model evidence.' },
  { icon: ScanFace, title: 'Deepfake detection', text: 'Every detected face is analysed independently with its own deepfake probability.' },
  { icon: Bot, title: 'AI-generated detection', text: 'Identifies fully synthetic images from diffusion and GAN generators.' },
  { icon: Flame, title: 'Explainable evidence', text: 'Heatmaps, ELA maps and region boxes show exactly where the evidence lies.' },
  { icon: Wand2, title: 'Intelligent restoration', text: 'Reconstruct flagged or hand-marked regions — always labelled as AI-reconstructed.' },
  { icon: FileText, title: 'Reports & dashboard', text: 'One-click forensic PDF reports, plus a dashboard tracking verdict trends and recent investigations.' },
  { icon: Film, title: 'Video deepfake analysis', text: 'Frame-by-frame face analysis with a suspicion timeline that jumps straight to the most suspicious moments.' },
  { icon: Lock, title: 'Private by design', text: 'JWT-secured accounts. Every image, analysis and report is isolated per user.' },
]

const STEPS = [
  { icon: Upload, title: 'Upload', text: 'Images up to 10 MB or videos up to 100 MB, validated server-side.' },
  { icon: Cpu, title: 'Preprocess', text: 'Orientation, normalisation, hashing and EXIF extraction.' },
  { icon: Microscope, title: 'Forensics', text: 'Error level, sensor-noise and frequency-domain analysis.' },
  { icon: Brain, title: 'Detection', text: 'Deepfake and AI-generated models run on CPU in seconds.' },
  { icon: Crosshair, title: 'Localise', text: 'Suspicious regions and faces are boxed in pixel coordinates.' },
  { icon: Eye, title: 'Explain', text: 'Heatmap plus a plain-English summary and uncertainty note.' },
  { icon: Wand2, title: 'Restore', text: 'Optional inpainting of the flagged area, clearly labelled.' },
  { icon: ClipboardCheck, title: 'Report', text: 'PDF report generated and saved to your history.' },
]

const COMPARE = [
  ['Verdict', 'Binary "real / fake" label', 'Confidence-scored verdict with uncertainty notes'],
  ['Coverage', 'One check — metadata or a single model', 'Forensic heuristics + deepfake + AI-generated models'],
  ['Explainability', 'Black-box output', 'Heatmaps, region boxes and per-signal reasoning'],
  ['Recovery', 'Not offered', 'Labelled AI restoration of flagged regions'],
  ['Accessibility', 'Expert desktop tools or paid enterprise SaaS', 'Self-serve web app with dashboard and reports'],
  ['Auditability', 'No record of past checks', 'Per-user history and downloadable reports'],
]

const STACK = ['PyTorch', 'Hugging Face', 'OpenCV', 'FastAPI', 'PostgreSQL', 'React', 'Docker']

function SectionHeading({ eyebrow, title, text }) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <p className="text-sm font-semibold text-cyan-600">{eyebrow}</p>
      <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">{title}</h2>
      {text ? <p className="mt-4 text-base leading-7 text-slate-600">{text}</p> : null}
    </div>
  )
}

export default function Landing() {
  const { user } = useAuth()
  const primaryTo = user ? '/analyze' : '/register'
  return (
    <div className="min-h-screen bg-white">
      <PublicNav />

      {/* Hero */}
      <section className="dark-surface relative overflow-hidden bg-navy-900 text-white">
        <div className="grid-bg absolute inset-0" aria-hidden />
        <div className="absolute left-1/2 top-0 h-[480px] w-[900px] -translate-x-1/2 rounded-full bg-cyan-500/15 blur-[120px]" aria-hidden />
        <div className="relative mx-auto max-w-7xl px-4 pb-0 pt-20 text-center sm:px-6 md:pt-28 lg:px-8">
          <div className="mx-auto max-w-3xl animate-fadeIn">
            <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium text-slate-300">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> Explainable AI image forensics
            </span>
            <h1 className="mt-6 text-4xl font-semibold leading-[1.08] tracking-tight text-white sm:text-5xl lg:text-6xl">
              Verify any image.
              <br />
              <span className="text-slate-400">Understand every verdict.</span>
            </h1>
            <p className="mx-auto mt-6 max-w-2xl text-lg leading-8 text-slate-300">
              TruthLens detects deepfakes, AI-generated content and photo manipulation in images and short videos, then
              shows the evidence: heatmaps, suspicious regions, frame-by-frame timelines and a forensic PDF report.
            </p>
            <div className="mt-9 flex flex-wrap justify-center gap-3">
              <Link to={primaryTo} className="btn-primary h-11 px-5 text-[15px]">
                {user ? 'Analyze an image' : 'Start for free'} <ArrowRight className="h-4 w-4" aria-hidden />
              </Link>
              <a href="#workflow" className="btn h-11 border border-white/15 px-5 text-[15px] text-white hover:bg-white/10">
                How it works
              </a>
            </div>
          </div>

          {/* Product shot */}
          <div className="relative mx-auto mt-16 max-w-6xl">
            <div className="rounded-t-2xl border border-b-0 border-white/10 bg-white/5 p-2 pb-0 shadow-2xl backdrop-blur sm:p-3 sm:pb-0">
              <div className="overflow-hidden rounded-t-lg border border-b-0 border-white/10 bg-white">
                <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-50 px-4 py-2.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-slate-300" />
                  <span className="h-2.5 w-2.5 rounded-full bg-slate-300" />
                  <span className="h-2.5 w-2.5 rounded-full bg-slate-300" />
                  <span className="mx-auto hidden rounded-md bg-white px-3 py-0.5 text-[11px] text-slate-400 ring-1 ring-slate-200 sm:block">
                    truthlens.app/analyses/8
                  </span>
                </div>
                <img
                  src="/product-shot.webp"
                  alt="TruthLens analysis report showing a manipulated image with the edited region highlighted"
                  className="block w-full"
                  width="2400"
                  height="1350"
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Stack strip */}
      <section className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-col items-center gap-4 px-4 py-8 sm:px-6 md:flex-row md:justify-between lg:px-8">
          <p className="text-sm text-slate-500">Built on proven open-source technology</p>
          <ul className="flex flex-wrap items-center justify-center gap-x-8 gap-y-2">
            {STACK.map((s) => (
              <li key={s} className="text-sm font-semibold tracking-tight text-slate-400">{s}</li>
            ))}
          </ul>
        </div>
      </section>

      {/* Problem */}
      <section id="problem" className="scroll-mt-20 bg-white py-20 md:py-28">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <SectionHeading
            eyebrow="The problem"
            title="Seeing is no longer believing"
            text="Generative AI made convincing fakes cheap and instant. Forensic verification is still expert-only and opaque. TruthLens makes it automated, explainable and accessible."
          />
          <dl className="mx-auto mt-14 grid max-w-5xl overflow-hidden rounded-2xl border border-slate-200 md:grid-cols-3">
            {STATS.map((s, i) => (
              <div key={s.value} className={`p-8 text-center ${i ? 'border-t border-slate-200 md:border-l md:border-t-0' : ''}`}>
                <dt className="text-4xl font-semibold tracking-tight text-slate-900">{s.value}</dt>
                <dd className="mt-3 text-sm leading-6 text-slate-600">{s.label}</dd>
                <dd className="mt-2 text-xs text-slate-400">{s.source}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="scroll-mt-20 border-y border-slate-200 bg-slate-50 py-20 md:py-28">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <SectionHeading
            eyebrow="Platform"
            title="Everything you need to investigate an image"
            text="Detection, explanation, recovery and reporting in one workflow."
          />
          <div className="mt-14 grid gap-px overflow-hidden rounded-2xl border border-slate-200 bg-slate-200 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <div key={title} className="bg-white p-7">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cyan-50 text-cyan-600 ring-1 ring-inset ring-cyan-100">
                  <Icon className="h-5 w-5" aria-hidden />
                </div>
                <h3 className="mt-5 text-[15px] font-semibold text-slate-900">{title}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-600">{text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Workflow */}
      <section id="workflow" className="scroll-mt-20 bg-white py-20 md:py-28">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <SectionHeading eyebrow="How it works" title="From upload to evidence in seconds" text="An eight-stage pipeline runs on every image." />
          <ol className="mt-14 grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map(({ icon: Icon, title, text }, i) => (
              <li key={title} className="relative border-t border-slate-200 pt-6">
                <span className="absolute -top-px left-0 h-px w-12 bg-cyan-600" aria-hidden />
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs font-medium text-cyan-600">{String(i + 1).padStart(2, '0')}</span>
                  <Icon className="h-4 w-4 text-slate-400" aria-hidden />
                </div>
                <h3 className="mt-3 text-[15px] font-semibold text-slate-900">{title}</h3>
                <p className="mt-1.5 text-sm leading-6 text-slate-600">{text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Comparison */}
      <section className="border-t border-slate-200 bg-slate-50 py-20 md:py-28">
        <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
          <SectionHeading eyebrow="Why TruthLens" title="Beyond a black-box label" />
          <div className="mt-14 overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-card">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-xs font-medium text-slate-500">
                  <th className="px-6 py-3.5 font-medium">Criteria</th>
                  <th className="px-6 py-3.5 font-medium">Existing tools</th>
                  <th className="px-6 py-3.5 font-medium text-slate-900">TruthLens</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {COMPARE.map(([k, a, b]) => (
                  <tr key={k}>
                    <td className="px-6 py-4 font-medium text-slate-900">{k}</td>
                    <td className="px-6 py-4 text-slate-500">
                      <span className="flex items-start gap-2"><Minus className="mt-0.5 h-4 w-4 shrink-0 text-slate-300" aria-hidden />{a}</span>
                    </td>
                    <td className="px-6 py-4 text-slate-700">
                      <span className="flex items-start gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden />{b}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="dark-surface relative overflow-hidden bg-navy-900">
        <div className="absolute right-0 top-0 h-80 w-[600px] rounded-full bg-cyan-500/15 blur-[100px]" aria-hidden />
        <div className="relative mx-auto flex max-w-7xl flex-col items-start justify-between gap-8 px-4 py-16 sm:px-6 md:flex-row md:items-center lg:px-8">
          <div>
            <h2 className="text-3xl font-semibold tracking-tight text-white">Verify your first image in under a minute.</h2>
            <p className="mt-3 max-w-xl text-slate-400">Create a free account and get an explainable verdict, heatmaps and a downloadable report.</p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-3">
            <Link to={primaryTo} className="btn-primary h-11 px-5 text-[15px]">
              {user ? 'Go to Analyze' : 'Create free account'} <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
            {!user ? (
              <Link to="/login" className="btn h-11 border border-white/15 px-5 text-[15px] text-white hover:bg-white/10">
                Sign in
              </Link>
            ) : null}
          </div>
        </div>
      </section>

      <PublicFooter />
    </div>
  )
}
