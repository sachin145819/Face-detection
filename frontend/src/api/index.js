import client from './client.js'

export const authApi = {
  register: (body) => client.post('/auth/register', body).then((r) => r.data),
  login: (body) => client.post('/auth/login', body).then((r) => r.data),
  me: () => client.get('/auth/me').then((r) => r.data),
}

export const imagesApi = {
  upload: (file, onUploadProgress) => {
    const fd = new FormData()
    fd.append('file', file)
    return client.post('/images', fd, { onUploadProgress }).then((r) => r.data)
  },
  list: () => client.get('/images').then((r) => r.data),
  get: (id) => client.get(`/images/${id}`).then((r) => r.data),
  remove: (id) => client.delete(`/images/${id}`),
}

export const analysesApi = {
  create: (imageId) => client.post('/analyses', { image_id: imageId }).then((r) => r.data),
  get: (id) => client.get(`/analyses/${id}`).then((r) => r.data),
  restore: (id, body) => client.post(`/analyses/${id}/restore`, body).then((r) => r.data),
}

export const videosApi = {
  upload: (file, onUploadProgress) => {
    const fd = new FormData()
    fd.append('file', file)
    // Videos can be large: no request timeout for the upload itself.
    return client.post('/videos', fd, { onUploadProgress, timeout: 0 }).then((r) => r.data)
  },
  list: () => client.get('/videos').then((r) => r.data),
  get: (id) => client.get(`/videos/${id}`).then((r) => r.data),
  remove: (id) => client.delete(`/videos/${id}`),
}

export const videoAnalysesApi = {
  // Runs synchronously on the server (typically 10–30 s, longer on slow CPUs).
  create: (videoId) => client.post('/video-analyses', { video_id: videoId }, { timeout: 600000 }).then((r) => r.data),
  get: (id) => client.get(`/video-analyses/${id}`).then((r) => r.data),
}

export const historyApi = {
  list: ({ q, verdict, media, page = 1, page_size = 10 } = {}) => {
    const params = { page, page_size }
    if (q) params.q = q
    if (verdict) params.verdict = verdict
    if (media) params.media = media
    return client.get('/history', { params }).then((r) => r.data)
  },
}

export const dashboardApi = {
  stats: () => client.get('/dashboard/stats').then((r) => r.data),
}

export const healthApi = {
  get: () => client.get('/health').then((r) => r.data),
}
