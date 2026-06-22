# RecruitIQ — AI-Augmented Recruitment Platform

**Screen 1,000 CVs. Surface the 10 who matter. Explain why.**

| Assignment | Category | Group Size | Marks |
|------------|----------|------------|-------|
| #5 of 15 | HR AI | 5 Students | 15 + 3 Bonus |

---

## Problem

Recruiters are drowning in volume. ATS keyword matching is brittle — it rejects great
candidates and waves through keyword-stuffed CVs. RecruitIQ goes **beyond keyword matching**
to semantic understanding of fit, ranks candidates with a transparent score breakdown,
explains every decision, flags bias, and writes tailored interview questions.

## What it does

- **JD parsing** — extracts role, seniority, required experience, hard/soft skills,
  must-have vs nice-to-have, domain knowledge, and education from any JD format.
- **CV batch ingestion** — PDF / DOCX / TXT, parsed into structured profiles
  (skills, experience, education, projects, achievements).
- **Semantic ranking** — embedding similarity + interpretable sub-scores, not keyword counts.
- **Explainable rankings** — per-candidate summary, strengths, gaps, risk flags, and a
  hire recommendation.
- **Bias & diversity flags** — detects a homogeneous shortlist and surfaces qualified
  "hidden gem" candidates with non-traditional backgrounds.
- **Tailored interview questions** — reference each candidate's actual projects, skills, and gaps.
- **Recruiter Copilot** — chat over the candidate pool.
- **Exports** — CSV shortlist + per-candidate PDF.

---

## Architecture

```
Next.js 15 (App Router, Tailwind 4)            FastAPI (async, in-memory store)
┌──────────────────────────────┐              ┌─────────────────────────────────────┐
│ Setup → Processing → Results  │   REST/JSON  │ /api/jd          parse JD             │
│  • JD input + CV dropzone     │ ───────────▶ │ /api/screen      batch screen (async) │
│  • live progress              │              │ /api/jobs/{id}   progress             │
│  • ranked list + score rings  │ ◀─────────── │ /api/results/{id}                     │
│  • candidate drawer           │              │ /api/candidates/{id}                  │
│  • diversity panel + copilot  │              │ /api/chat /compare /export            │
└──────────────────────────────┘              └─────────────────────────────────────┘
                                                          │
                                            ┌─────────────┴───────────────┐
                                            │ Google Gemini               │
                                            │  • 2.5-flash-lite (parse,    │
                                            │    explain, questions, chat) │
                                            │  • embedding-001 (ranking)   │
                                            │  • heuristic fallback engine │
                                            └──────────────────────────────┘
```

No database — everything lives in memory for the process lifetime (resets on restart),
which is all the assignment needs.

### Pipeline (how a screening runs)

1. **Parse CVs in batches** (many CVs per LLM call) with capped concurrency.
2. **Embed** the JD + all CVs in one batched embedding call.
3. **Score & rank locally** (no API): cosine similarity + sub-scores.
4. **Explain** the shortlist + hidden gems in batched LLM calls; the rest get instant
   deterministic explanations.

This keeps a 20–25 CV batch **well under 60 s** and within the free-tier rate limits.

### Scoring formula

```
Overall =
  32% Skill match     (must-haves weighted 2× vs nice-to-haves)
+ 25% Semantic fit    (JD↔CV embedding cosine similarity)
+ 18% Experience      (years vs required, capped)
+ 10% Domain          (semantic proximity)
+  7% Education
+  8% Soft skills
```

---

## Quick start

### Local (recommended for development)

```bash
# 1. Backend
cd backend
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env        # then add your GEMINI_API_KEY (optional)
uvicorn app.main:app --reload --port 8000

# 2. Frontend (new terminal)
cd frontend
npm install
npm run dev                        # http://localhost:3000
```

### Docker

```bash
cp .env.example .env
docker compose up --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Swagger docs | http://localhost:8000/docs |

In the UI: paste a JD (or click **Use sample**) → **Parse requirements** → drop CVs (or
**Load 25 sample CVs**) → **Screen candidates**.

---

## ⚠️ Gemini API key & quota (read this)

The app defaults to **`gemini-2.5-flash-lite`**. Two things to know:

- **`gemini-2.0-flash` has zero free quota** and 429s instantly — do not use it.
  `gemini-2.5-flash` and `-lite` work.
- **The free tier is tiny** (~20 generate requests/day, ~10/min per model). That's enough
  to *try* the app a couple of times per day, but for a reliable live demo you should
  **enable billing** on your Google AI Studio / Cloud project. flash-lite is ~$0.10 / 1M
  input tokens — a full 25-CV screening costs well under $0.01.

If the key is missing or quota is exhausted, the app **degrades gracefully** to a
deterministic heuristic engine (a circuit breaker skips the API after a daily-quota hit),
so it never crashes — ranking still works via embeddings, and explanations fall back to a
specific, CV-aware heuristic. The header shows whether AI is live or offline.

---

## Deployment

- **Backend → Render** (`render.yaml` blueprint, Docker). Set env vars in the dashboard:
  `GEMINI_API_KEY`, `DEMO_MODE=false`, `CORS_ORIGINS=https://<your-vercel-app>.vercel.app`.
- **Frontend → Vercel** (root `frontend/`). Set `NEXT_PUBLIC_API_URL=https://<your-render-app>.onrender.com`.

---

## Project layout

```
backend/app/
  main.py        FastAPI app + CORS + health
  config.py      settings (model, batch sizes, rate-limit knobs)
  gemini.py      Gemini client: retry/backoff, concurrency cap, circuit breaker, embeddings
  ai.py          JD/CV parsing, explanations, questions, chat + heuristic fallbacks
  ranking.py     semantic + structured scoring
  diversity.py   bias flags + hidden-gem detection
  pipeline.py    screening orchestration (batched, async, progress)
  documents.py   PDF/DOCX/TXT text extraction
  routers.py     REST endpoints
  report.py      CSV + PDF export
  store.py       in-memory data store
  schemas.py     Pydantic models
  tests/         deterministic offline pipeline tests

frontend/src/
  app/page.tsx              workspace (setup → processing → results)
  components/recruit/       setup, results, detail drawer, diversity panel, copilot, ui-bits
  lib/api.ts                typed API client
sample-data/                1 JD + 25 sample CVs (also bundled in frontend/public/samples)
```

## Tests

```bash
cd backend && source venv/bin/activate && pytest
```

Tests run in offline heuristic mode (no API/quota needed) and lock in document extraction,
the scoring math, strong-beats-weak ranking, missing-must-have detection, the full async
screening pipeline, and diversity flagging.
