import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { AlertCircle, Eye, EyeOff, LogIn } from 'lucide-react'
import AuthLayout from './AuthLayout.jsx'
import Spinner from '../components/Spinner.jsx'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../context/ToastContext.jsx'
import { errorMessage } from '../api/client.js'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export default function Login() {
  const { login } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const location = useLocation()
  const [form, setForm] = useState({ email: '', password: '' })
  const [touched, setTouched] = useState({})
  const [show, setShow] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const errors = {
    email: !form.email ? 'Email is required' : !EMAIL_RE.test(form.email) ? 'Enter a valid email address' : '',
    password: !form.password ? 'Password is required' : '',
  }
  const invalid = Object.values(errors).some(Boolean)

  const onSubmit = async (e) => {
    e.preventDefault()
    setTouched({ email: true, password: true })
    if (invalid) return
    setBusy(true)
    setError('')
    try {
      const u = await login(form.email.trim(), form.password)
      toast.success(`Welcome back, ${u?.name?.split(' ')[0] || 'there'}!`)
      const from = location.state?.from
      navigate(from && from !== '/login' ? from : '/dashboard', { replace: true })
    } catch (err) {
      setError(errorMessage(err, 'Invalid email or password.'))
    } finally {
      setBusy(false)
    }
  }

  const field = (name) => ({
    id: name,
    name,
    value: form[name],
    onChange: (e) => setForm((f) => ({ ...f, [name]: e.target.value })),
    onBlur: () => setTouched((t) => ({ ...t, [name]: true })),
    'aria-invalid': Boolean(touched[name] && errors[name]),
    'aria-describedby': touched[name] && errors[name] ? `${name}-err` : undefined,
    className: `input ${touched[name] && errors[name] ? 'input-error' : ''}`,
  })

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Welcome back. Sign in to continue your investigations."
      footer={<>New to TruthLens? <Link to="/register" className="font-semibold text-cyan-700 hover:underline">Create an account</Link></>}
    >
      <form onSubmit={onSubmit} noValidate className="space-y-5">
        {error ? (
          <div className="flex items-start gap-2 rounded-xl bg-red-50 px-3.5 py-3 text-sm text-red-700 ring-1 ring-inset ring-red-200" role="alert">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {error}
          </div>
        ) : null}
        <div>
          <label htmlFor="email" className="label">Email</label>
          <input type="email" autoComplete="email" placeholder="you@example.com" {...field('email')} />
          {touched.email && errors.email ? <p id="email-err" className="mt-1.5 text-xs text-red-600">{errors.email}</p> : null}
        </div>
        <div>
          <label htmlFor="password" className="label">Password</label>
          <div className="relative">
            <input type={show ? 'text' : 'password'} autoComplete="current-password" placeholder="••••••••" {...field('password')} />
            <button type="button" onClick={() => setShow((s) => !s)} className="absolute inset-y-0 right-0 flex items-center rounded-r-xl px-3 text-slate-400 hover:text-slate-600" aria-label={show ? 'Hide password' : 'Show password'}>
              {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          {touched.password && errors.password ? <p id="password-err" className="mt-1.5 text-xs text-red-600">{errors.password}</p> : null}
        </div>
        <button type="submit" className="btn-dark w-full py-3" disabled={busy}>
          {busy ? <Spinner className="h-4 w-4" /> : <LogIn className="h-4 w-4" aria-hidden />}
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </AuthLayout>
  )
}
