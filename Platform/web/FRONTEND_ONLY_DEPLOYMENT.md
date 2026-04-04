# Vercel Frontend Deployment Guide (with Local Backend)

## Overview
- **Frontend**: Hosted on Vercel (public, accessible from anywhere)
- **Backend**: Runs locally on your machine (port 8081)
- **Connection**: Frontend connects to backend via **ngrok tunnel**

---

## Step 1: Deploy Frontend to Vercel (5 mins)

### 1.1 Create Vercel Project
1. Go to https://vercel.com
2. Sign up or sign in
3. Click **"Add New"** → **"Project"**
4. Click **"Import Git Repository"**
5. Find and select: `UrekMazino/okxStatBot`

### 1.2 Configure Project
- **Framework Preset**: Next.js (auto-detected)
- **Root Directory**: `Platform/web` ✅
- Leave build settings as default
- Click **"Deploy"**

Wait 2-3 minutes for deployment to complete. You'll get a URL like: `https://okxstatbot.vercel.app`

---

## Step 2: Connect to Local Backend via ngrok

### 2.1 Install ngrok
1. Download from https://ngrok.com/download
2. Sign up at https://ngrok.com
3. Get your auth token from dashboard

### 2.2 Start ngrok Tunnel
```bash
# Authenticate ngrok (one time)
ngrok config add-authtoken YOUR_AUTH_TOKEN_HERE

# Start tunnel to your local backend
ngrok http 8081
```

You'll see output like:
```
Session Status    online
Forwarding        https://abc-123-xyz-789.ngrok.io -> http://localhost:8081
```

**Copy the ngrok URL** (e.g., `https://abc-123-xyz-789.ngrok.io`)

### 2.3 Update Vercel Environment Variables

1. Go to your Vercel project
2. Click **"Settings"** → **"Environment Variables"**
3. Add two variables:

| Key | Value |
|-----|-------|
| `NEXT_PUBLIC_API_BASE` | `https://YOUR-NGROK-URL.ngrok.io/api/v2` |
| `NEXT_PUBLIC_WS_BASE` | `wss://YOUR-NGROK-URL.ngrok.io` |

4. Click **"Save"**
5. Click **"Deployments"** → **"Redeploy"** on the latest deployment

Wait for redeploy to complete (2-3 mins).

---

## Step 3: Start Your Local Backend

In a terminal, start your backend:
```bash
cd Platform/api
python -m uvicorn app.main:app --reload --port 8081
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8081
```

---

## Step 4: Test the Connection

1. Go to your Vercel URL (e.g., `https://okxstatbot.vercel.app`)
2. Try logging in or accessing the dashboard
3. Check browser console for any errors

If you see API errors, verify:
- ✅ ngrok tunnel is running
- ✅ Backend is running locally
- ✅ Vercel env vars use the correct ngrok URL

---

## Troubleshooting

### "Cannot connect to API"
- Check ngrok is running: `ngrok http 8081` should show `online`
- Verify ngrok URL in Vercel env vars matches
- Check browser console for exact error

### "WebSocket connection failed"
- Make sure `NEXT_PUBLIC_WS_BASE` starts with `wss://`
- Use ngrok URL, not localhost

### ngrok URL keeps changing
- One-time setup: Use `ngrok config add-authtoken`
- With auth token, ngrok remembers your URL after restart
- If URL still changes: Update Vercel env var with new URL

### How to update ngrok URL
1. Stop ngrok (Ctrl+C)
2. Run `ngrok http 8081`
3. Copy new URL
4. Update Vercel environment variables
5. Redeploy on Vercel
6. Restart backend

---

## Daily Workflow

1. **Morning**: Start ngrok tunnel
   ```bash
   ngrok http 8081
   ```

2. **Then**: Start your backend
   ```bash
   cd Platform/api
   python -m uvicorn app.main:app --reload --port 8081
   ```

3. **Access from anywhere**: Go to your Vercel URL

4. **Evening**: Stop both (Ctrl+C in each terminal)

---

## When Away from Computer

⚠️ **Important**: Since your backend runs locally, you can only use the dashboard when:
- Your computer is on
- ngrok tunnel is running
- Backend is running

**To make it always-on, deploy backend to Render** (see other guide).

---

## Next Steps

- ✅ Frontend deployed
- ✅ Backend connected via ngrok
- ✅ Testing complete

Enjoy your remote dashboard! 🚀

Questions? Check the logs in Vercel and ngrok terminals.
