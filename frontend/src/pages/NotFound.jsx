import { Link } from 'react-router-dom'
import { SearchX } from 'lucide-react'
import { LogoMark } from '../components/Logo.jsx'

export default function NotFound() {
  return (
    <div className="dark-surface relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-navy-900 px-4 text-center text-white">
      <div className="grid-bg absolute inset-0" aria-hidden />
      <div className="relative">
        <LogoMark className="mx-auto h-14 w-14" />
        <p className="mt-8 font-serif text-8xl font-bold text-cyan-400">404</p>
        <h1 className="mt-4 flex items-center justify-center gap-2 font-serif text-2xl font-semibold">
          <SearchX className="h-6 w-6 text-violet-400" aria-hidden /> Nothing to inspect here
        </h1>
        <p className="mx-auto mt-2 max-w-md text-slate-400">The page you're looking for doesn't exist or may have been moved.</p>
        <div className="mt-8 flex justify-center gap-3">
          <Link to="/" className="btn-primary">Back to home</Link>
          <Link to="/dashboard" className="btn text-white ring-1 ring-inset ring-white/20 hover:bg-white/10">Dashboard</Link>
        </div>
      </div>
    </div>
  )
}
