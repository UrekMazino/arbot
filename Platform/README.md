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

1. Base URL: `http://localhost:8081/api/v2`
2. Health: `GET /api/v2/health`
3. Swagger: `http://localhost:8081/docs`

Bootstrap admin (default):

1. Email: `admin@okxstatbot.local`
2. Password: `ChangeMeNow123!`

## Next Slice

1. Add web frontend scaffold (`Platform/web`)
2. Add integration tests for ingest -> DB -> websocket flow
3. Add run/trade writer bridge from V1 runtime into V2 API (beyond event-only ingest)
4. Add auth hardening for ingest (`event_ingest_key` mandatory outside local dev)
