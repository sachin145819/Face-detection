# TruthLens — Frontend

React 18 + Vite 5 + Tailwind CSS 3 + React Router 6 + Recharts + lucide-react.

## Running locally

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173  (proxies /api -> http://localhost:8000)
```

Start the backend on port 8000 first (see the root README), e.g.

```bash
cd backend && .venv/bin/uvicorn app.main:app --port 8000
```

Other scripts:

| Command | What it does |
|---|---|
| `npm run build` | Production build into `dist/` |
| `npm run preview` | Serve the built `dist/` on :4173 (also proxies `/api`) |
| `npm run lint` | ESLint (flat config) |

## Structure

```
src/
  api/        axios client (JWT header, 401 -> logout) + endpoint wrappers (docs/CONTRACT.md §5)
  context/    AuthContext (user, login, register, logout), ToastContext
  components/ AppShell (sidebar/drawer), ImageViewer, BoxOverlay, CompareSlider, RegionEditor,
              RestorationPanel, SignalCard, ScoreGauge, VerdictBadge, UploadZone, …
  pages/      Landing, Login, Register, Dashboard, Analyze, Result, History, NotFound
  lib/        withToken() for binary URLs, verdict colours, formatting, debounce
```

The app always calls relative `/api/...` URLs. Binary endpoints (images, heatmaps, ELA, restorations,
PDF reports) are loaded via `withToken(url)` which appends `?token=<jwt>`. The JWT is kept in
`localStorage` under `truthlens_token`.
