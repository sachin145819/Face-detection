import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertCircle, Eye, EyeOff, UserPlus, Check } from 'lucide-react'
import AuthLayout from './AuthLayout.jsx'
import Spinner from '../components/Spinner.jsx'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../context/ToastContext.jsx'
import { errorMessage } from '../api/client.js'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export default function Register() {
  const { register } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', email: '', password: '', confirm: '' })
  const [touched, setTouched] = useState({})
  const [show, setShow] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const errors = {
    name: !form.name.trim() ? 'Name is required' : form.name.trim().length < 2 ? 'Name is too short' : '',
    email: !form.email ? 'Email is required' : !EMAIL_RE.test(form.email) ? 'Enter a valid email address' : '',
    password: !form.password ? 'Password is required' : form.password.length < 8 ? 'Password must be at least 8 characters' : '',
    confirm: form.confirm !== form.password ? 'Passwords do not match' : '',
  }
  const invalid = Object.values(errors).some(Boolean)

  const onSubmit = async (e) => {
    e.preventDefault()
    setTouched({ name: true, email: true, password: true, confirm: true })
    if (invalid) return
    setBusy(true)
    setError('')
    try {
      await register(form.name.trim(), form.email.trim(), form.password)
      toast.success('Account created — welcome to TruthLens!')
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(errorMessage(err, 'Could not create your account.'))
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
  const err = (name) => (touched[name] && errors[name] ? <p id={`${name}-err`} className="mt-1.5 text-xs text-red-600">{errors[name]}</p> : null)

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Start verifying images with explainable AI forensics."
      footer={<>Already have an account? <Link to="/login" className="font-semibold text-cyan-700 hover:underline">Sign in</Link></>}
    >
      <form onSubmit={onSubmit} noValidate className="space-y-5">
        {error ? (
          <div className="flex items-start gap-2 rounded-xl bg-red-50 px-3.5 py-3 text-sm text-red-700 ring-1 ring-inset ring-red-200" role="alert">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {error}
          </div>
        ) : null}
        <div>
          <label htmlFor="name" className="label">Full name</label>
          <input type="text" autoComplete="name" placeholder="Ada Lovelace" {...field('name')} />
          {err('name')}
        </div>
        <div>
          <label htmlFor="email" className="label">Email</label>
          <input type="email" autoComplete="email" placeholder="you@example.com" {...field('email')} />
          {err('email')}
        </div>
        <div>
          <label htmlFor="password" className="label">Password</label>
          <div className="relative">
            <input type={show ? 'text' : 'password'} autoComplete="new-password" placeholder="At least 8 characters" {...field('password')} />
            <button type="button" onClick={() => setShow((s) => !s)} className="absolute inset-y-0 right-0 flex items-center rounded-r-xl px-3 text-slate-400 hover:text-slate-600" aria-label={show ? 'Hide password' : 'Show password'}>
              {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          {err('password') || (
            <p className={`mt-1.5 flex items-center gap-1 text-xs ${form.password.length >= 8 ? 'text-green-600' : 'text-slate-400'}`}>
              <Check className="h-3 w-3" aria-hidden /> Minimum 8 characters
            </p>
          )}
        </div>
        <div>
          <label htmlFor="confirm" className="label">Confirm password</label>
          <input type={show ? 'text' : 'password'} autoComplete="new-password" placeholder="Repeat password" {...field('confirm')} />
          {err('confirm')}
        </div>
        <button type="submit" className="btn-dark w-full py-3" disabled={busy}>
          {busy ? <Spinner className="h-4 w-4" /> : <UserPlus className="h-4 w-4" aria-hidden />}
          {busy ? 'Creating account…' : 'Create account'}
        </button>
      </form>
    </AuthLayout>
  )
}
