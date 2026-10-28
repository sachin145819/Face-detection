import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev/preview proxy target; override with API_TARGET=http://host:port when running a second backend.
const API = process.env.API_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.VITE_PORT) || 5173,
    proxy: {
      '/api': { target: API, changeOrigin: true },
      '/docs': { target: API, changeOrigin: true },
      '/openapi.json': { target: API, changeOrigin: true },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      '/api': { target: API, changeOrigin: true },
      '/docs': { target: API, changeOrigin: true },
      '/openapi.json': { target: API, changeOrigin: true },
    },
  },
  build: {
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          charts: ['recharts'],
        },
      },
    },
  },
})
