# OKXStatBot Dashboard - Vercel Deployment Guide

## Quick Start (3 minutes)

### Step 1: Deploy Frontend to Vercel

1. Go to [vercel.com](https://vercel.com) and sign up (free)
2. Click "New Project"
3. Import your GitHub repository (UrekMazino/okxStatBot)
4. Configure the project:
   - **Root Directory**: `Platform/web`
   - **Framework Preset**: Next.js
   - **Build Command**: `npm run build`
   - **Start Command**: `npm start`
   - **Install Command**: `npm ci`

5. Add Environment Variables:
   - `NEXT_PUBLIC_API_BASE`: See Step 2 below
   - `NEXT_PUBLIC_WS_BASE`: See Step 2 below

6. Click "Deploy"

---

## Step 2: Connect to Your Local Backend

You have two options:

### ✅ Option A: Use ngrok (Easiest, Free)

Tunnel your local backend to a public URL:

1. Download ngrok: https://ngrok.com/download
2. Sign up and get auth token
3. Run in a terminal in your project:
   ```bash
   ngrok http 8081
   ```
4. Copy the public URL (looks like: `https://abc-123-def-456.ngrok.io`)
5. Update Vercel environment variables:
   - `NEXT_PUBLIC_API_BASE`: `https://abc-123-def-456.ngrok.io/api/v2`
   - `NEXT_PUBLIC_WS_BASE`: `wss://abc-123-def-456.ngrok.io`
6. Redeploy on Vercel (trigger a new build)

**Note:** ngrok URL changes when you restart, so you'll need to update Vercel env vars each time.

---

### 🚀 Option B: Deploy Backend Too (More Permanent)

Deploy backend to Render free tier:

1. Go to [render.com](https://render.com)
2. New > Web Service
3. Connect GitHub repo
4. Configure:
   - **Root Directory**: `Platform/api`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port 8081`
   - **Environment**: Python 3.11

5. Add environment variables (same ones your `.env` file uses)
6. Use Render backend URL in Vercel env vars:
   - `NEXT_PUBLIC_API_BASE`: `https://your-api.onrender.com/api/v2`
   - `NEXT_PUBLIC_WS_BASE`: `wss://your-api.onrender.com`

**Pros:** 
- No need to keep local backend running
- URL stays the same
- Free tier (may spin down after inactivity)

**Cons:**
- Requires managing secrets and database
- May need PostgreSQL (Render offers free tier)

---

## Testing Locally Before Deploying

```bash
# Terminal 1: Start backend
cd Platform/api
python -m uvicorn app.main:app --reload --port 8081

# Terminal 2: Start frontend  
cd Platform/web
npm run dev
```

Open http://localhost:3000

---

## Troubleshooting

### "Cannot connect to API"
- Check that backend is running and accessible
- Verify env vars match your actual backend URL
- Try ngrok URL in browser directly to test connectivity

### "WebSocket connection failed"
- Ensure `NEXT_PUBLIC_WS_BASE` is set correctly
- For ngrok: use `wss://` (websocket secure)

### CORS errors
- Backend needs to allow your Vercel domain
- Update CORS settings in `Platform/api/app/`

---

## Next Steps

After successful deployment, you can:
- Access dashboard from anywhere: `https://your-vercel-app.vercel.app`
- Monitor bot runs live from your phone
- Control bot remotely

Enjoy your hosted dashboard! 🚀
