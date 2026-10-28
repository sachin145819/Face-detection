import axios from 'axios'
import { getToken } from '../lib/token.js'

const client = axios.create({ baseURL: '/api', timeout: 180000 })

let unauthorizedHandler = null
export function setUnauthorizedHandler(fn) {
  unauthorizedHandler = fn
}

client.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

client.interceptors.response.use(
  (res) => res,
  (error) => {
    const status = error?.response?.status
    const url = error?.config?.url || ''
    const isAuthAttempt = url.includes('/auth/login') || url.includes('/auth/register')
    if (status === 401 && !isAuthAttempt && unauthorizedHandler) {
      unauthorizedHandler()
    }
    return Promise.reject(error)
  },
)

/** Extract a human readable message from an API error ({detail}) */
export function errorMessage(error, fallback = 'Something went wrong. Please try again.') {
  if (!error) return fallback
  const res = error.response
  if (!res) {
    if (error.code === 'ECONNABORTED') return 'The request timed out. Please try again.'
    return 'Cannot reach the TruthLens server. Is the backend running?'
  }
  const detail = res.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d) => {
        const field = Array.isArray(d.loc) ? d.loc.filter((p) => p !== 'body').join('.') : ''
        return field ? `${field}: ${d.msg}` : d.msg
      })
      .join('; ')
  }
  if (res.status === 413) return 'File is too large (max 10 MB).'
  if (res.status >= 500) return 'Server error. Please try again shortly.'
  return fallback
}

export default client
