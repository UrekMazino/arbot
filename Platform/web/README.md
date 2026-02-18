# V2 Web Frontend

This is the V2 web UI scaffold (Next.js + TypeScript) for:

1. Run browser (list runs + status + PnL + duration)
2. Charts (equity curve + drawdown + strategy/regime attribution table)
3. Event timeline (switches, gates, alerts, exits) with source/severity/category filters
4. Live websocket event stream merged into run detail timeline (`/ws/dashboard`)
5. Data quality + reconciliation panels (status, deltas, top alerts, issue list)
6. Config snapshot viewer + report artifact links (download endpoints)
7. Super admin console (`/admin`) for:
   - bot start/stop/status,
   - live terminal log tail,
   - historical logs/reports listing,
   - `.env` setting edits,
   - user/role management.

## Local Run (without Docker)

```bash
cd Platform/web
copy .env.example .env.local
npm install
npm run dev
```

Open: `http://127.0.0.1:3000`
Super admin: `http://127.0.0.1:3000/admin`

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

1. Current frontend covers V2-A items 1-5.
2. Super admin console requires a superuser account.
3. Auth is token-based via `/api/v2/auth/login`.
4. Bot start/stop from `/admin` uses API-side process control and expects `Execution/main_execution.py` to be runnable from the API container.
