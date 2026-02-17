# V2 UI Platform Spec

Date: 2026-02-18
Status: Draft for implementation
Owner: OKXStatBot

## 1. Objectives

Build a web platform for the bot with these capabilities:

1. Realtime monitoring dashboard.
2. Report generation module.
3. Web-first architecture that can be extended to an online service.
4. Database-backed storage for operational and analytics data.
5. Login and session management.
6. User management with role-based access.

## 2. Architecture Decisions

Use an API-first architecture with clean separation between execution engine and UI.

Core components:

1. `web` frontend: Next.js (React, TypeScript).
2. `api` backend: FastAPI + SQLAlchemy + Alembic.
3. `db`: PostgreSQL.
4. `cache/realtime`: Redis.
5. `worker`: RQ (Redis Queue) for report jobs and background tasks.
6. `storage`: local disk now, S3-compatible later for report files.

Why this is best for this bot:

1. Works with your existing Python execution stack.
2. Supports low-latency realtime updates.
3. Scales to multi-user and hosted deployments.
4. Keeps auth and API server-side for security.

Critical boundary decision:

1. Bot should not directly write primary operational records to PostgreSQL.
2. Bot emits events to API ingest endpoints.
3. API persists to DB and publishes realtime updates.
4. Bot can use local spool fallback if API/Redis is temporarily unavailable.

## 3. Runtime Data Flow

### 3.1 Live Monitoring Flow

1. Bot emits structured runtime events.
2. API ingests events and writes to Postgres.
3. API publishes event updates to Redis channels/streams.
4. Frontend subscribes via WebSocket and updates dashboard in realtime.

### 3.2 Reporting Flow

1. User requests report generation from UI.
2. API enqueues background job.
3. Worker executes report generation and writes outputs to storage.
4. Worker updates report status and file list in DB.
5. UI shows progress and download links.

## 4. Project Layout (Proposed)

```text
OKXStatBot/
  Platform/
    api/
      app/
        main.py
        core/
        models/
        schemas/
        services/
        routers/
        realtime/
      alembic/
      requirements.txt
    web/
      src/
        app/
        components/
        features/
        lib/
      package.json
    worker/
      worker.py
      tasks/
  Execution/
  Reports/
  Logs/
```

## 5. Event and Data Contracts

### 5.1 Bot Event Emitter Contract (Critical)

Implementation location:

1. New module: `Execution/func_event_emitter.py`
2. Called from `Execution/main_execution.py` and `Execution/func_trade_management.py` at lifecycle points.

Canonical event envelope:

```python
{
    "event_id": "uuid",
    "run_id": "uuid",
    "bot_instance_id": "uuid",
    "ts": 1739635200.123,
    "event_type": "trade_close",
    "severity": "info",
    "payload": {}
}
```

Required fields:

1. `event_id` (uuid, idempotency key)
2. `run_id`
3. `bot_instance_id`
4. `ts` (unix timestamp float)
5. `event_type`
6. `severity` (`info|warn|error|critical`)
7. `payload` (event-specific json)

Required minimum events:

1. `heartbeat` (every cycle, 30-60 seconds)
2. `regime_update` (on regime change and periodic status)
3. `strategy_update` (on strategy change and periodic status)
4. `trade_open`
5. `trade_close`
6. `pair_switch`
7. `risk_alert`
8. `report_status`

Optional events:

1. `entry_reject`
2. `gate_enforced`
3. `reconciliation_warning`
4. `data_quality_warning`

Emit points in existing code (minimum):

1. `main_execution.py`:
- post regime decision
- post strategy decision
- pair switch attempt/success/fail
- per-cycle heartbeat
2. `func_trade_management.py`:
- trade open
- trade close
- key gate enforcement and risk alerts

Primary storage path:

1. Bot -> `POST /api/v2/bots/{bot_instance_id}/events/batch`
2. API -> PostgreSQL `run_events`
3. API -> Redis publish `bot:{bot_instance_id}:events`

### 5.2 Ingestion Reliability, Idempotency, and Retention

1. API deduplicates by `event_id` (unique index).
2. Bot batches events (for example 10-100 events/batch).
3. On API failure, bot writes local spool file and retries.
4. Retention policy:
- hot events: 90 days
- archive/compress older records
- keep trade and run summary data long-term

### 5.3 Database Schema (MVP)

### 5.3.1 Auth and User Management

1. `users`
- `id`, `email`, `password_hash`, `is_active`, `is_superuser`, `created_at`, `updated_at`

2. `roles`
- `id`, `name` (`admin`, `trader`, `viewer`), `description`

3. `user_roles`
- `user_id`, `role_id`

4. `refresh_tokens`
- `id`, `user_id`, `token_hash`, `expires_at`, `revoked_at`, `created_at`, `ip`, `user_agent`

5. `audit_logs`
- `id`, `actor_user_id`, `action`, `resource_type`, `resource_id`, `metadata_json`, `created_at`

### 5.3.2 Bot Operations and Runtime State

1. `bot_instances`
- `id`, `name`, `environment` (`demo`, `live`), `is_active`, `created_at`

2. `runs`
- `id`, `bot_instance_id`, `run_key`, `start_ts`, `end_ts`, `status`, `start_equity`, `end_equity`, `session_pnl`, `max_drawdown`

3. `run_events`
- `id`, `event_id`, `run_id`, `bot_instance_id`, `ts`, `event_type`, `severity`, `payload_json`

4. `trades`
- `id`, `run_id`, `pair_key`, `entry_ts`, `exit_ts`, `side`, `entry_z`, `exit_z`, `pnl_usdt`, `hold_minutes`, `strategy`, `regime`, `exit_reason`

5. `strategy_metrics`
- `id`, `run_id`, `strategy`, `trades`, `wins`, `losses`, `win_rate_pct`, `pnl_usdt`, `avg_hold_minutes`

6. `regime_metrics`
- `id`, `run_id`, `regime`, `time_pct`, `switches`, `gate_blocks`

7. `bot_configs`
- `id`, `run_id`, `config_snapshot_json`, `created_at`

8. `alerts`
- `id`, `run_id`, `event_id`, `severity`, `alert_type`, `message`, `acknowledged`, `acknowledged_by`, `acknowledged_at`, `created_at`

9. `position_snapshots`
- `id`, `run_id`, `ts`, `pair_key`, `notional_usdt`, `unrealized_pnl_usdt`, `entry_z`, `current_z`, `hold_minutes`

10. `pair_performance_mv` (materialized view first)
- derived from `trades` by `run_id` and `pair_key`
- avoid write-heavy duplicate table in initial release

### 5.3.3 Analytics and Overfitting Schema

Extend `trades` with required attribution fields:

1. `entry_strategy`
2. `entry_regime`
3. `exit_tier` (`tier_5_profit`, `tier_1_stop`, `tier_2_coint`, etc.)
4. `entry_z_threshold_used`
5. `size_multiplier_used`

Derived analytics artifacts:

1. Strategy x regime scorecard (win rate, expectancy, drawdown contribution)
2. Parameter stability summary by run and period
3. Walk-forward segment metrics

### 5.4 Reporting

1. `reports`
- `id`, `run_id`, `status` (`queued`, `running`, `done`, `failed`), `requested_by`, `requested_at`, `finished_at`, `error_text`

2. `report_files`
- `id`, `report_id`, `name`, `path`, `mime_type`, `size_bytes`, `checksum`, `created_at`

## 6. API Contract (MVP)

Base path: `/api/v2`

### 6.1 Auth

1. `POST /auth/login`
2. `POST /auth/refresh`
3. `POST /auth/logout`
4. `GET /auth/me`

### 6.2 Bot Event Ingestion

1. `POST /bots/{bot_instance_id}/events/batch`
2. `POST /bots/{bot_instance_id}/heartbeat`

### 6.3 User Management

1. `GET /users`
2. `POST /users`
3. `PATCH /users/{user_id}`
4. `POST /users/{user_id}/roles`
5. `DELETE /users/{user_id}/roles/{role}`

### 6.4 Runs and Monitoring

1. `GET /runs`
2. `GET /runs/{run_id}`
3. `GET /runs/{run_id}/events`
4. `GET /runs/{run_id}/trades`
5. `GET /runs/{run_id}/metrics/strategy`
6. `GET /runs/{run_id}/metrics/regime`
7. `GET /runs/{run_id}/analytics/scorecard`
8. `GET /runs/{run_id}/analytics/walk-forward`
9. `GET /runs/{run_id}/analytics/parameter-stability`

### 6.5 Reports

1. `POST /runs/{run_id}/reports/generate`
2. `GET /runs/{run_id}/reports`
3. `GET /reports/{report_id}`
4. `GET /reports/{report_id}/files`
5. `GET /reports/{report_id}/files/{file_id}/download`

### 6.6 Realtime

1. `GET /ws/dashboard?bot_instance_id={id}`

WebSocket event types:

1. `heartbeat`
2. `status_update`
3. `strategy_update`
4. `regime_update`
5. `trade_open`
6. `trade_close`
7. `risk_alert`
8. `report_status`

### 6.6.1 WebSocket Payload Schemas

`heartbeat`:

```json
{
  "event_type": "heartbeat",
  "ts": 1739635200.123,
  "payload": {
    "cycle": 1234,
    "uptime_seconds": 3600,
    "in_position": true,
    "current_pair": "ETH-USDT-SWAP/SOL-USDT-SWAP",
    "equity_usdt": 10523.45,
    "session_pnl_usdt": 23.45
  }
}
```

`regime_update`:

```json
{
  "event_type": "regime_update",
  "ts": 1739635200.123,
  "payload": {
    "regime": "TREND",
    "previous_regime": "RANGE",
    "confidence": 0.85,
    "allow_new_entries": true,
    "reason_codes": ["strong_trend", "vol_expansion"]
  }
}
```

`strategy_update`:

```json
{
  "event_type": "strategy_update",
  "ts": 1739635200.123,
  "payload": {
    "strategy": "TREND_SPREAD",
    "previous_strategy": "STATARB_MR",
    "allow_new_entries": true,
    "reason_codes": ["regime_trend"]
  }
}
```

`trade_open`:

```json
{
  "event_type": "trade_open",
  "ts": 1739635200.123,
  "payload": {
    "pair": "ETH-USDT-SWAP/SOL-USDT-SWAP",
    "side": "SELL_SPREAD",
    "entry_z": 2.84,
    "strategy": "TREND_SPREAD",
    "regime": "TREND"
  }
}
```

`trade_close`:

```json
{
  "event_type": "trade_close",
  "ts": 1739635200.123,
  "payload": {
    "pair": "ETH-USDT-SWAP/SOL-USDT-SWAP",
    "pnl_usdt": 12.34,
    "pnl_pct": 0.87,
    "strategy": "STATARB_MR",
    "regime": "RANGE",
    "hold_minutes": 142,
    "exit_reason": "profit_target_reached",
    "exit_tier": "tier_5_profit"
  }
}
```

`pair_switch`:

```json
{
  "event_type": "pair_switch",
  "ts": 1739635200.123,
  "payload": {
    "from_pair": "A/B",
    "to_pair": "C/D",
    "reason": "cointegration_lost"
  }
}
```

`risk_alert`:

```json
{
  "event_type": "risk_alert",
  "ts": 1739635200.123,
  "payload": {
    "severity": "warn",
    "alert_type": "tier_1_stop",
    "message": "Hard stop triggered",
    "pair": "A/B"
  }
}
```

`report_status`:

```json
{
  "event_type": "report_status",
  "ts": 1739635200.123,
  "payload": {
    "report_id": "uuid",
    "run_id": "uuid",
    "status": "running",
    "progress_pct": 45
  }
}
```

## 7. Background Job System (Decision)

Decision: use `RQ` with Redis.

Why:

1. Lower operational complexity than Celery for this workload.
2. Reuses Redis already required for realtime.
3. Sufficient for report and analytics jobs.

Worker setup:

```bash
rq worker --url redis://localhost:6379 reports analytics
```

Queue and job conventions:

1. Queue `reports`: report generation and rebuild.
2. Queue `analytics`: scorecard/materialized views refresh.
3. Job states mirrored into `reports.status` and event stream.

## 8. Authentication and Security

1. Password hashing: Argon2id.
2. Access tokens: JWT (short TTL, for example 15 min).
3. Refresh tokens: DB-backed, revocable, rotated.
4. Role-based access control:
- `admin`: full control, user management.
- `trader`: runs, reports, bot operations.
- `viewer`: read-only dashboard and reports.
5. Audit log required for:
- login/logout,
- user/role changes,
- report generation requests,
- critical bot control actions.
6. Rate limit login and refresh endpoints.
7. Encrypt exchange keys at rest (`pgcrypto` or equivalent KMS-backed encryption).
8. Never expose raw secrets in WebSocket payloads, logs, or report exports.

## 9. Frontend Modules (MVP)

1. `Dashboard`
- live PnL, equity, open position, regime, strategy, health.

2. `Runs`
- run list, filters, drilldown.

3. `Run Detail`
- event timeline, trades table, strategy/regime panels, charts.

4. `Reports`
- generate, monitor status, download artifacts.

5. `Admin`
- users, roles, account status, audit logs.

6. `Analytics`
- strategy x regime heatmap
- overfit flags
- walk-forward and parameter stability views

## 10. Integration Strategy with Existing V1

Use a staged integration to avoid blocking live bot improvements.

1. Stage 1 (read-only): ingest existing `Reports/v1` and `Logs/v1` into DB.
2. Stage 2 (live): add structured event emitter in execution loop.
3. Stage 3 (control): add authenticated bot control endpoints if needed.

## 11. Non-Functional Targets

1. Dashboard update latency: under 2 seconds for live cards.
2. API P95 latency: under 300 ms for normal read endpoints.
3. Report jobs: resilient retry on transient failures.
4. Zero plaintext secrets in logs.
5. Daily DB backup and restore test procedure.

## 12. Testing Strategy

### 12.1 Unit Tests

1. API endpoints (`pytest` + `httpx`).
2. DB models and migrations.
3. Event emitter payload validation.
4. Worker task unit tests.

### 12.2 Integration Tests

1. Bot -> API ingest -> DB -> WebSocket flow.
2. WebSocket subscription and reconnect behavior.
3. Report generation end-to-end.
4. Auth flow (`login`, `refresh`, `logout`).

### 12.3 Load Tests

1. WebSocket: 100 concurrent clients.
2. API: 1000 requests/min sustained on core read endpoints.
3. Worker: 10 concurrent report jobs.

### 12.4 Test Data and Fixtures

1. Seed users: `admin`, `trader`, `viewer`.
2. Fixture runs with 100+ trades.
3. Mock bot event stream at 1 Hz for dashboard/load tests.

## 13. Delivery Plan

### V2.1 Foundation (1-2 weeks)

1. FastAPI service scaffold.
2. Postgres schema and migrations.
3. Auth and RBAC.
4. Run list and run detail APIs.

### V2.2 Realtime Dashboard (1-2 weeks)

1. WebSocket channel.
2. Live dashboard page.
3. Event timeline stream.

### V2.3 Reports Module (1 week)

1. Report job queue and worker.
2. Report generation endpoints.
3. Report pages and file downloads.

### V2.4 Admin and Hardening (1 week)

1. User management UI.
2. Audit log UI.
3. Security and deployment hardening.

## 14. Deployment Strategy

### 14.1 Local Development

Use Docker Compose:

1. PostgreSQL
2. Redis
3. API (hot reload)
4. RQ worker
5. Next.js app

### 14.2 Production Phase 1 (Single VPS)

1. Nginx reverse proxy with TLS.
2. API + worker managed by systemd/supervisor.
3. PostgreSQL and Redis (managed or self-hosted).
4. Centralized logging and basic alerting.

### 14.3 Production Phase 2 (Scale Out)

1. Multiple API instances behind load balancer.
2. Multiple workers by queue.
3. Managed PostgreSQL and Redis.
4. CDN for static assets.

### 14.4 Secrets Management

1. Development: `.env` files (`gitignored`).
2. Production: environment variables or vault service.
3. Bot API credentials encrypted at rest.

## 15. Rollback and Migration Strategy

1. Alembic migration history for all schema changes.
2. Backward compatible API versioning under `/api/v2`.
3. Feature flags for staged rollout:
- `realtime_ws`
- `event_ingest_v2`
- `analytics_scorecard_v2`
4. Blue/green or canary deploy where possible.
5. Daily DB backups, 30-day retention, monthly restore drill.
6. Event spool replay tool for ingest recovery.

## 16. Relationship to Deferred Engine Work

Deferred runtime upgrades remain queued under:

1. `V2_ROADMAP.md` section `V2-B`
2. `REGIME_ROUTER_PHASE4_SPEC.md`

UI work should not block these items, and these items should not block initial V2 UI delivery.
