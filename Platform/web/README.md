# V2 Web Frontend

This is the V2 web UI scaffold (Next.js + TypeScript) for:

1. Run browser (list runs + status + PnL + duration)
2. Run detail panel (events + trades)
3. Live websocket event preview (`/ws/dashboard`)

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

1. This is a foundation slice for roadmap V2-A item 1.
2. Charts/data-quality/config snapshot panels are next slices.
3. Auth is token-based via `/api/v2/auth/login`.
