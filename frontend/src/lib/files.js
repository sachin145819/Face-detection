import { getToken } from './token.js'

/**
 * Append `?token=<jwt>` to a relative binary URL returned by the API
 * (images, heatmaps, ELA maps, restorations, PDF reports) so it can be
 * used directly in <img src> / <a href>.
 */
export function withToken(url) {
  if (!url) return null
  const token = getToken()
  if (!token) return url
  const sep = url.includes('?') ? '&' : '?'
  return `${url}${sep}token=${encodeURIComponent(token)}`
}
