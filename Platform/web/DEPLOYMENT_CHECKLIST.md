# Vercel Deployment Checklist

## ❌ Delete Old Deployment (Fix the Error)

**If you already created a Vercel project:**

1. Go to https://vercel.com/dashboard
2. Find your project (likely named `okxstatbot`)
3. Click **Settings** → scroll to bottom → **Delete Project**
4. Confirm deletion

**Why?** The old config was looking for Python files. Starting fresh ensures clean deployment.

---

## ✅ Fresh Deployment (5 minutes)

### Step 1: Import Repository
1. Go to https://vercel.com
2. Click **"Add New"** → **"Project"**
3. Click **"Import Git Repository"**
4. Search for: `UrekMazino/okxStatBot`
5. Click **"Import"**

### Step 2: CRITICAL - Set Root Directory
**This is the most important step!**

In the "Configure Project" screen:
- **Root Directory**: Click the dropdown
- Select: `Platform/web` ← **Make sure it says this!**
- **Framework**: Should auto-detect as "Next.js" ✅
- Leave everything else default

### Step 3: Deploy
1. Click **"Deploy"**
2. Wait for build to complete (2-3 minutes)
3. You'll get a URL like: `https://okxstatbot-xyz.vercel.app`

---

## ✅ Connect ngrok (Local Backend Tunnel)

### Step 1: Get ngrok
```bash
# Download and install from https://ngrok.com/download
# Create account and copy your auth token
```

### Step 2: Start ngrok
```bash
ngrok config add-authtoken YOUR_AUTH_TOKEN_HERE
ngrok http 8081
```

You'll see:
```
Forwarding    https://abc-123-def-456.ngrok.io -> http://localhost:8081
```

**Copy that URL** (the `https://abc-123...` part)

### Step 3: Set Vercel Env Vars
1. Go to your Vercel project dashboard
2. Click **"Settings"** (top nav)
3. Click **"Environment Variables"** (left sidebar)
4. Click **"Add"** and add these TWO variables:

| Key | Value | Notes |
|-----|-------|-------|
| `NEXT_PUBLIC_API_BASE` | `https://YOUR-NGROK-URL.ngrok.io/api/v2` | Replace with your ngrok URL |
| `NEXT_PUBLIC_WS_BASE` | `wss://YOUR-NGROK-URL.ngrok.io` | Same URL but `wss://` prefix |

5. Click **"Save"**

### Step 4: Redeploy
1. Go to **"Deployments"** tab
2. Click the **three dots** on the latest deployment
3. Click **"Redeploy"**
4. Wait for build (2-3 mins)

---

## ✅ Start Local Backend

In a new terminal (keep ngrok running in another terminal):
```bash
cd Platform/api
python -m uvicorn app.main:app --reload --port 8081
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8081
```

---

## ✅ Test It!

1. Go to your Vercel URL (e.g., `https://okxstatbot-xyz.vercel.app`)
2. Try logging in
3. Check the dashboard
4. If errors, check browser console (F12)

---

## 🆘 Troubleshooting

### Still seeing Python error?
- ❌ Delete the Vercel project
- ✅ Start completely fresh
- ✅ Make SURE you select `Platform/web` as root directory

### "Cannot connect to API"
- Check ngrok is running: `ngrok http 8081`
- Check Vercel env vars match ngrok URL exactly
- Check backend is running: `python -m uvicorn app.main:app --reload --port 8081`

### "WebSocket error"
- Verify `NEXT_PUBLIC_WS_BASE` starts with `wss://` (not `ws://`)
- Use the same ngrok URL as API_BASE

### ngrok session expired
- Restart: `ngrok http 8081` (same URL if auth token is set)
- Update Vercel env vars only if URL changed
- Redeploy on Vercel

---

## 🎉 Done!

Your frontend is live and connected to your local backend!

Access from anywhere using: `https://your-vercel-url.vercel.app`
