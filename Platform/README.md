# Platform (V2)

This folder contains the V2 web platform foundation:

1. `api`: FastAPI service (`/api/v2`)
2. `worker`: RQ background worker for reports/analytics
3. `docker-compose.yml`: local Postgres + Redis + API + worker stack

## Quick Start (Local)

```bash
cd Platform
docker compose up --build
```

API:

1. Base URL: `http://localhost:8080/api/v2`
2. Health: `GET /api/v2/health`
3. Swagger: `http://localhost:8080/docs`

Bootstrap admin (default):

1. Email: `admin@okxstatbot.local`
2. Password: `ChangeMeNow123!`

## Next Slice

1. Add web frontend scaffold (`Platform/web`)
2. Wire Redis pub/sub fanout for `ws/dashboard`
3. Add bot-side event emitter module in `Execution/`
4. Add integration tests for ingest -> DB -> websocket flow

