# Platform (V2)

This folder contains the V2 web platform foundation:

1. `api`: FastAPI service (`/api/v2`)
2. `worker`: RQ background worker for reports/analytics
3. `web`: Next.js UI scaffold (run browser + run detail + live feed)
4. `docker-compose.yml`: local Postgres + Redis + API + worker + web stack

## Quick Start (Local)

```bash
cd Platform
docker compose up --build
```

API:

1. Base URL: `http://localhost:8081/api/v2`
2. Health: `GET /api/v2/health`
3. Swagger: `http://localhost:8081/docs`

Web:

1. URL: `http://localhost:3000`
2. See `Platform/web/README.md` for local non-docker run.

Bootstrap admin (default):

1. Email: `sirceojraiv@gmail.com`
2. Password: `ChangeMeNow123!`

## Next Slice

1. Add integration tests for ingest -> DB -> websocket flow
2. Add run/trade writer bridge from V1 runtime into V2 API (beyond event-only ingest)
3. Add auth hardening for ingest (`event_ingest_key` mandatory outside local dev)
4. Add charts, data-quality panel, and config snapshot panel in web UI
