# Deploy FastAPI Backend to Render

## Quick Overview
- **Frontend**: Vercel (already deployed ✅)
- **Backend**: Render (what we're doing now)
- **Database**: PostgreSQL on Render (free tier)
- **Total time**: ~15 minutes

---

## Step 1: Create Render Account

1. Go to https://render.com
2. Click **"Sign up"** (or sign in if you have an account)
3. Create account with GitHub (easier for deployment)
4. Authorize Render to access your GitHub repos

---

## Step 2: Create PostgreSQL Database (Free Tier)

1. In Render dashboard, click **"New"** → **"PostgreSQL"**
2. Fill in:
   - **Name**: `okxstatbot-db`
   - **Database**: `okxstatbot_db`
   - **User**: `okxstatbot`
   - **Region**: Choose closest to you
   - **Plan**: Free
3. Click **"Create Database"**
4. **IMPORTANT**: Copy the connection string that appears
   - It looks like: `postgresql://user:password@host:port/database`
   - Save this somewhere! You'll need it soon.

Wait ~2-3 minutes for database to be created.

---

## Step 3: Create Web Service for Backend

1. Click **"New"** → **"Web Service"**
2. Click **"Build and deploy from a Git repository"**
3. Click **"Connect account"** and authorize GitHub
4. Find and select: `UrekMazino/okxStatBot`

### Configure Web Service
Fill in these settings:

| Field | Value |
|-------|-------|
| **Name** | `okxstatbot-api` |
| **Root Directory** | `Platform/api` |
| **Environment** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn app:app --host 0.0.0.0 --port 10000` |
| **Plan** | Free |

---

## Step 4: Add Environment Variables

**BEFORE deploying**, scroll down and click **"Advanced"** → **"Environment"**

Add these environment variables:

### Required Variables

| Key | Value |
|-----|-------|
| `DATABASE_URL` | Paste your PostgreSQL connection string from Step 2 |
| `CORS_ORIGINS` | `https://projecty-six.vercel.app` (or your Vercel URL) |
| `JWT_SECRET_KEY` | Generate a random string (e.g., use https://www.uuidgenerator.net/ and copy some characters) |

### Optional Variables (if needed)
```
REDIS_URL = (optional, leave blank if not using)
ENVIRONMENT = production
```

---

## Step 5: Deploy

1. Click **"Create Web Service"**
2. Wait for build to complete (3-5 minutes)
3. You'll get a URL like: `https://okxstatbot-api.onrender.com`
4. **Save this URL!** You'll need it for Vercel.

Check the **Logs** tab if it fails:
- Look for error messages
- Most common: Database connection issues or missing env vars

---

## Step 6: Update Vercel Environment Variables

1. Go to https://vercel.com/dashboard
2. Click `projecty-six`
3. **Settings** → **Environment Variables**
4. Update these variables with your Render backend URL:

```
NEXT_PUBLIC_API_BASE = https://okxstatbot-api.onrender.com/api/v2
NEXT_PUBLIC_WS_BASE = wss://okxstatbot-api.onrender.com
```

5. Click **Save**

---

## Step 7: Redeploy Frontend

1. Go to **Deployments** tab
2. Click three dots ⋯ on latest deployment
3. Click **Redeploy**
4. Wait for build to complete (2-3 mins)

---

## Step 8: Test

1. Go to `https://projecty-six.vercel.app`
2. Try logging in
3. You should now be able to access your dashboard from anywhere! 🎉

---

## Troubleshooting

### "Failed to fetch" on Vercel
- Check Vercel env vars are set correctly
- Check Render backend is online (green status in Render dashboard)
- Wait a few minutes for Vercel redeploy to complete

### Render shows "Failed to build"
- Check **Logs** tab in Render
- Common issues:
  - Database connection string is wrong
  - Missing environment variables
  - Python version incompatibility

### Database connection failed
- Verify `DATABASE_URL` is copied exactly from Render
- Make sure database is in "Available" state
- Try restarting the web service

### Login doesn't work
- Check `JWT_SECRET_KEY` is set (random string, doesn't need to be special)
- Check `CORS_ORIGINS` includes your Vercel URL with `https://`

---

## Important Notes

- ✅ Render free tier is limited (sleeps after 15 mins of inactivity)
- ✅ Database is included and always on
- ✅ Perfect for testing/development
- ✅ Total cost: $0

When you deploy:
- First request wakes up the service (~5 second delay)
- Subsequent requests are instant
- If no traffic for 15 mins, it sleeps again

---

## Next Steps

After successful deployment:
1. ✅ Frontend on Vercel (24/7 online)
2. ✅ Backend on Render (24/7 online)
3. ✅ Database on Render (24/7 online)
4. ✅ No ngrok needed
5. ✅ Access dashboard from phone/anywhere!

You can now monitor your bot from anywhere! 🚀
