# Deployment guide (Render backend + Vercel frontend)

Both Render and Vercel build from GitHub. The rebuild is committed locally — it
must be **pushed** before either platform can deploy it.

> ⚠️ Version match: the new backend serves `/api/...` (the old one served
> `/api/v1/...`). The new frontend calls `/api/...`. Deploy **both** new versions
> together, or the live site breaks.

---

## Step 0 — Push the code to GitHub

The live Vercel app deploys from `main`, so merge there and push (this rebuilds
the frontend too):

```bash
git checkout main
git merge optimize-credits-and-deploy
git push origin main
```

(Or push the feature branch for a Vercel **preview** first:
`git push origin optimize-credits-and-deploy`.)

---

## Step 1 — Deploy the backend on Render

**Easiest (Blueprint):**
1. Render Dashboard → **New → Blueprint**.
2. Connect the GitHub repo → Render reads `render.yaml` and proposes the
   `recruitiq-backend` web service (Docker, rootDir `backend`).
3. When prompted for the synced secret, set **`GEMINI_API_KEY`** = your key
   (the `AQ.`-prefixed one). Leave it blank to run in offline heuristic mode.
4. **Apply** → first build takes a few minutes.

**Manual alternative:** New → **Web Service** → connect repo → Root Directory
`backend` → Runtime **Docker** (auto-detects the Dockerfile) → add env vars
(below) → Create.

Env vars (the blueprint pre-fills all but the key):

| Key | Value |
|-----|-------|
| `GEMINI_API_KEY` | your key (secret) |
| `DEMO_MODE` | `false` |
| `CORS_ORIGINS` | `https://ai-recruitment-platform-theta.vercel.app` |
| `CORS_ORIGIN_REGEX` | `https://.*\.vercel\.app` |

Don't set `PORT` — Render injects it and the Dockerfile binds it.

When it's live, copy the URL (e.g. `https://recruitiq-backend.onrender.com`) and verify:
```bash
curl https://<your-render-url>.onrender.com/health
# -> {"status":"healthy","ai":true,"model":"gemini-2.5-flash-lite"}
```

> Free tier sleeps after ~15 min idle; the first request then takes ~50s to wake.

---

## Step 2 — Point the Vercel frontend at the Render backend

1. Vercel → your project → **Settings → Environment Variables**.
2. Add `NEXT_PUBLIC_API_URL = https://<your-render-url>.onrender.com`
   (no trailing slash), for Production.
3. **Redeploy** the frontend (Deployments → ⋯ → Redeploy). `NEXT_PUBLIC_*` is
   baked in at build time, so a redeploy is required after changing it.
4. Confirm the Root Directory is `frontend` (Settings → General).

---

## Step 3 — Verify live

Open https://ai-recruitment-platform-theta.vercel.app → the header should show
**"AI live · gemini-2.5-flash-lite"** (or "Offline heuristic mode" if no key /
quota). Run: Use sample → Parse → Load 25 sample CVs → Screen candidates.

If you see CORS errors in the browser console, double-check `CORS_ORIGINS` on
Render exactly matches the Vercel URL (scheme + host, no trailing slash).

---

## Free-tier note (Gemini)

~20 generate requests/day per model. Screen ~8–12 CVs per run to make real-AI
runs count; ranking always works (embeddings have separate quota); the app falls
back to the heuristic engine when quota is exhausted. Enable billing to lift the
cap (flash-lite ≈ $0.01 per screening).
