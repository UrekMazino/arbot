# OKXStatBot v1 Free Deployment

This v1 deployment path runs the full app in one Docker Compose stack:

- Next.js dashboard
- FastAPI backend
- PostgreSQL
- Redis
- report worker
- bot runner
- independent pair-supply runner
- Caddy reverse proxy
- optional Cloudflare Quick Tunnel for a free HTTPS preview URL

## Recommended Free Host

Use an Oracle Cloud Always Free Ubuntu VM if you want the full bot online. The app has long-running workers and trading processes, so serverless-only hosts such as Vercel are not enough for the full stack.

Suggested VM:

- Shape: `VM.Standard.A1.Flex`
- CPU/RAM: start with `2 OCPU / 12 GB RAM`; use `4 OCPU / 24 GB RAM` if your region has capacity
- Disk: `80-100 GB`
- OS: Ubuntu 24.04 or 22.04

If Oracle says capacity is unavailable, retry another availability domain or later. Keep budget alerts enabled even when staying inside Always Free limits.

## Server Setup

SSH into the VM, then install Docker:

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
newgrp docker
docker version
docker compose version
```

Clone the repo:

```bash
git clone https://github.com/UrekMazino/arbot.git OKXStatBot
cd OKXStatBot
```

## Configure Secrets

Create the production env files:

```bash
cp Platform/.env.v1.example Platform/.env.v1
cp Platform/runtime/Execution.env.example Platform/runtime/Execution.env
```

Generate secrets:

```bash
openssl rand -hex 32
openssl rand -hex 32
openssl rand -hex 32
```

Edit `Platform/.env.v1`:

- Replace `POSTGRES_PASSWORD`.
- Replace `ACCESS_TOKEN_SECRET`.
- Replace `REFRESH_TOKEN_SECRET`.
- Replace `EVENT_INGEST_KEY`.
- Set `BOOTSTRAP_ADMIN_EMAIL`.
- Set `BOOTSTRAP_ADMIN_PASSWORD`.
- For first deploy with Cloudflare Quick Tunnel, keep `PUBLIC_SITE_ADDRESS=:80`.

Edit `Platform/runtime/Execution.env`:

- Add OKX demo credentials first.
- Keep `OKX_FLAG=1` for demo.
- Keep `STATBOT_DRY_RUN=1` until the online stack is verified.
- Set `STATBOT_EVENT_INGEST_KEY` to the exact same value as `EVENT_INGEST_KEY`.

## First Online Deploy With Free HTTPS Tunnel

This uses a free Cloudflare Quick Tunnel. The URL changes when the tunnel container restarts, but it is the fastest free v1 path.

```bash
cd Platform
docker compose --env-file .env.v1 -f docker-compose.v1.yml --profile tunnel up -d --build
docker compose --env-file .env.v1 -f docker-compose.v1.yml logs -f cloudflared
```

Open the `https://...trycloudflare.com` URL from the `cloudflared` logs.

Check the stack:

```bash
docker compose --env-file .env.v1 -f docker-compose.v1.yml ps
docker compose --env-file .env.v1 -f docker-compose.v1.yml logs -f api
```

## Stable Domain Deploy

When you have a domain pointing to the VM public IP, edit `Platform/.env.v1`:

```env
PUBLIC_SITE_ADDRESS=https://bot.example.com
PUBLIC_WEB_ORIGIN=https://bot.example.com
CORS_ORIGINS=https://bot.example.com
PASSWORD_RESET_LINK_BASE=https://bot.example.com/reset-password
ACME_EMAIL=you@example.com
```

Open inbound ports `80` and `443` in the VM firewall/security list, then run:

```bash
cd Platform
docker compose --env-file .env.v1 -f docker-compose.v1.yml up -d --build
```

Caddy will request and renew HTTPS certificates automatically.

## Operating v1

Useful commands:

```bash
cd Platform
docker compose --env-file .env.v1 -f docker-compose.v1.yml ps
docker compose --env-file .env.v1 -f docker-compose.v1.yml logs -f api bot-runner pair-supply-runner worker
docker compose --env-file .env.v1 -f docker-compose.v1.yml restart api web
docker compose --env-file .env.v1 -f docker-compose.v1.yml down
```

Database backup:

```bash
cd Platform
docker compose --env-file .env.v1 -f docker-compose.v1.yml exec -T postgres pg_dump -U okxbot okxbot_v2 > okxbot_v1_backup.sql
```

Restore later:

```bash
cd Platform
docker compose --env-file .env.v1 -f docker-compose.v1.yml exec -T postgres psql -U okxbot okxbot_v2 < okxbot_v1_backup.sql
```

## Safety Checklist Before Live Trading

- Confirm dashboard login works over `https://`.
- Confirm Pair Universe Start/Stop works.
- Confirm Bot Start/Stop works.
- Confirm events appear in Console and Dashboard.
- Confirm reports generate.
- Run in `OKX_FLAG=1` and `STATBOT_DRY_RUN=1` first.
- Only after verification, switch to live credentials, `OKX_FLAG=0`, and finally `STATBOT_DRY_RUN=0`.

## Why This Path

The full bot needs always-on background processes and shared local state. A single Docker Compose VM is simpler and more reliable for v1 than splitting the frontend, API, database, Redis, and workers across several free serverless services.
