# V2 Web Frontend

This is the V2 web UI scaffold (Next.js + TypeScript) for:

1. Run browser (list runs + status + PnL + duration)
2. Charts (equity curve + drawdown + strategy/regime attribution table)
3. Event timeline (switches, gates, alerts, exits) with source/severity/category filters
4. Live websocket event stream merged into run detail timeline (`/ws/dashboard`)

## Local Run (without Docker)

```bash
cd Platform/web
copy .env.example .env.local
npm install
npm run dev
```

Open: `http://127.0.0.1:3000`

Default backend target (from `.env.local`):

- `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8081/api/v2`
- `NEXT_PUBLIC_WS_BASE=ws://127.0.0.1:8081`

Use bootstrap admin credentials:

- Email: `admin@okxstatbot.dev`
- Password: `ChangeMeNow123!`

## Docker Compose (full stack)

From `Platform/`:

```bash
docker compose up --build
```

This includes:

1. `postgres`
2. `redis`
3. `api` (`http://127.0.0.1:8081`)
4. `worker`
5. `web` (`http://127.0.0.1:3000`)

## Notes

1. Current frontend covers V2-A items 1-3.
2. Next slices are data-quality/reconciliation and config snapshot/report links.
3. Auth is token-based via `/api/v2/auth/login`.
