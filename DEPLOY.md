# Deployment Guide: RA Project

Your app has two parts:

- **Frontend**: Vite + React in `frontend/RA-Project` (great for Vercel).
- **Backend**: Flask (Python) in `backend` with in-memory storage and OpenAI-based analysis.

## Can you do it all on Vercel?

**Frontend: yes.** Deploy the frontend on Vercel and it will work well.

**Backend: only with big changes.** Vercel runs your backend as **serverless functions**, not a long-lived Flask server. That leads to:

| Issue | Why it matters |
|-------|----------------|
| **No shared memory** | Your backend keeps uploads in `uploaded_datasets` in memory. On Vercel, each request can hit a different instance, so that in-memory store is not shared and data would disappear between requests. You’d need something like Vercel Blob, Vercel KV, or an external DB. |
| **Time limits** | Analysis runs 50 prompts through the OpenAI API. That can exceed Vercel’s limits (e.g. 60s on Pro, 300s on Enterprise). You might hit timeouts. |
| **File upload size** | Vercel has a 4.5 MB request body limit. Your app allows uploads up to 50 MB, so you’d need to use Vercel Blob (or similar) for large files. |

So: **you can’t just drop the current Flask app onto Vercel and have it behave the same.** You’d need to refactor to serverless (e.g. one function per route), add persistent storage, and possibly move long-running analysis to a queue or another service.

## Recommended: Frontend on Vercel, backend elsewhere

Easiest path:

1. **Deploy frontend on Vercel** (see below).
2. **Deploy backend on a service that runs a normal server**, e.g.:
   - [Railway](https://railway.app) (simple, good for Flask)
   - [Render](https://render.com) (free tier for web services)
   - [Fly.io](https://fly.io)
3. **Point the frontend at the deployed API** using the backend URL.

### 1. Deploy frontend to Vercel

- Push your code to GitHub (if you haven’t already).
- In [Vercel](https://vercel.com): **Add New Project** → import the repo.
- Set **Root Directory** to: `RA-Prototype/frontend/RA-Project`.
- Add an **Environment Variable**:
  - Name: `VITE_API_BASE_URL`
  - Value: `https://your-backend-url.com` (your deployed backend URL, no trailing slash).
- Deploy. Vercel will run `npm run build` and serve the `dist` folder (configured in `vercel.json`).

### 2. Deploy backend (e.g. Railway or Render)

- **Railway**: Create a new project, connect the repo, set root to `RA-Prototype/backend`. Add a `requirements.txt` if you don’t have one, set `OPENAI_API_KEY` in variables, and use a start command like `gunicorn app:app` (and install gunicorn in requirements).
- **Render**: New Web Service, connect repo, root `RA-Prototype/backend`, build command `pip install -r requirements.txt`, start command `gunicorn app:app`, add `OPENAI_API_KEY` in Environment.

After the backend is live, set `VITE_API_BASE_URL` on Vercel to that URL and redeploy the frontend if needed.

## If you insist on “all on Vercel”

You would need to:

1. Replace in-memory storage with **Vercel Blob** (and/or KV/DB) for uploads and analysis state.
2. Expose the Flask API as **Vercel serverless functions** (one handler per route, or a single handler that dispatches by path).
3. Either accept that long analyses may **time out** or move them to an external queue/worker and poll for results.

That’s a larger refactor; the “frontend on Vercel + backend on Railway/Render” approach is usually faster and more reliable for your current design.

---

## Deploy the entire app on Render

**Yes — you can run both frontend and backend on Render.** Use two Render services: one **Static Site** for the frontend and one **Web Service** for the Flask API. Both can live in the same repo.

### 1. Backend (Web Service)

1. In [Render](https://render.com): **New** → **Web Service**.
2. Connect your repo and set:
   - **Root Directory**: `RA-Prototype/backend`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
3. **Environment**:
   - Add `OPENAI_API_KEY` (your OpenAI API key).
4. Create the service. Note the URL (e.g. `https://ra-project-api.onrender.com`).

The backend uses `requirements.txt` and `gunicorn` in the repo; no extra config needed.

### 2. Frontend (Static Site)

1. In Render: **New** → **Static Site**.
2. Connect the same repo and set:
   - **Root Directory**: `RA-Prototype/frontend/RA-Project`
   - **Build Command**: `npm install && npm run build`
   - **Publish Directory**: `dist`
3. **Environment** (so the frontend talks to your backend):
   - Key: `VITE_API_BASE_URL`
   - Value: your backend URL from step 1, e.g. `https://ra-project-api.onrender.com` (no trailing slash).
4. Create the site. Render will build the Vite app and serve it (e.g. `https://ra-project.onrender.com`).

### 3. CORS

The Flask app already uses `flask-cors` with permissive CORS, so the frontend origin (e.g. `https://ra-project.onrender.com`) can call the backend without extra config.

### Free tier notes

- **Web Service**: Free instances spin down after ~15 minutes of no traffic; the first request after that may take 30–60 seconds to wake up.
- **Static Site**: Free and doesn’t spin down.
- If the frontend shows “network error” when calling the API, wait for the backend to wake up and try again, or consider Render’s paid tier to keep the backend always on.
