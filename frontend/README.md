# Finance System Frontend

Next.js 14 frontend for the finance-system dashboard. The app lives under `frontend/` and does not modify the Python backend under `src/`.

## Stack

- Next.js 14 App Router
- React + TypeScript
- Tailwind CSS
- shadcn-style local UI components
- `fetch` + `@tanstack/react-query`

## Run

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

## API Proxy

`next.config.js` rewrites frontend API calls:

```text
/api/:path* -> http://localhost:8000/:path*
```

The dashboard currently reads:

- `GET /api/wallets/assets`
- `GET /api/vendors/summary`

If those endpoints are unavailable, the UI falls back to local mock data so the dashboard remains usable during backend development.

## Money Rule

Frontend calculation uses integer minor units after API normalization. Formatting happens only at display time.
