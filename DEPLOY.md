# Deployment guide

The rebuild is committed locally on branch `optimize-credits-and-deploy`.
Render (backend) and Vercel (frontend) auto-deploy from GitHub.

Existing live URLs:
- Frontend (Vercel): `https://ai-recruitment-platform-theta.vercel.app` (currently the OLD build)
- Backend (Render): `https://ai-recruitment-platform-backend.onrender.com` (currently 503 / old build)

---

## 1. Push to GitHub (triggers auto-deploy)

**Option A — production (recommended once you've reviewed locally):**
```bash
git checkout main
git merge optimize-credits-and-deploy
git push origin main
```

**Option B — preview first (non-destructive):**
```bash
git push origin optimize-credits-and-deploy
```
Vercel builds a preview URL; merge to `main` later to promote to production.

---

## 2. Render (backend) dashboard env vars

Service: `ai-recruitment-platform-backend`. Set under **Environment**:

| Key | Value |
|-----|-------|
| `GEMINI_API_KEY` | your key (the `AQ.`-prefixed one) |
| `DEMO_MODE` | `false` |
| `CORS_ORIGINS` | `https://ai-recruitment-platform-theta.vercel.app` |
| `CORS_ORIGIN_REGEX` | `https://.*\.vercel\.app` (allows preview URLs) |

Render injects `$PORT` automatically — don't set it. The Dockerfile binds it.
Free tier sleeps after ~15 min idle (first request after sleep takes ~50s to wake).

## 3. Vercel (frontend) dashboard

- **Root directory:** `frontend`
- **Environment variable:** `NEXT_PUBLIC_API_URL = https://ai-recruitment-platform-backend.onrender.com`
- Redeploy after setting it (Next.js bakes `NEXT_PUBLIC_*` in at build time).

---

## 4. Verify live

```bash
curl https://ai-recruitment-platform-backend.onrender.com/health
# -> {"status":"healthy","ai":true,"model":"gemini-2.5-flash-lite"}
```
Then open the Vercel URL → Load 25 sample CVs → Screen candidates.

---

## Free-tier demo tips (no billing)

Gemini free tier ≈ **20 generate requests/day** per model. To make real-AI runs count:
- **Screen ~8–12 CVs per run** (not 25) → ~3–4 LLM calls → up to ~5 real-AI runs/day.
- Embeddings have a separate, larger quota, so **ranking always works**, even after the
  generate quota is gone.
- When the daily quota is hit, a circuit breaker switches to the heuristic engine instantly
  (no hanging), and the header shows "Offline heuristic mode". Explanations are still
  candidate-specific, just rule-based instead of LLM-written.
- Quota resets daily — do your final graded demo run on a fresh day, first thing.
