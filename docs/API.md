# RecruitIQ — API Reference

Base URL: `http://localhost:8000`
Interactive docs (always current): `http://localhost:8000/docs`

All endpoints are under `/api` except `/health` and `/`.

---

## Health

`GET /health` → `{ "status": "healthy", "ai": true, "model": "gemini-2.5-flash-lite" }`

`ai` is `false` when no key is set or the daily quota is exhausted (offline heuristic mode).

---

## Job description

### `POST /api/jd/text`
Parse a pasted JD.
```json
{ "text": "Senior Backend Engineer. 5+ years Python, FastAPI, PostgreSQL..." }
```

### `POST /api/jd`  (multipart)
Parse an uploaded JD file. Field: `file` (PDF/DOCX/TXT) **or** `text`.

**Response** (both): `JDResponse`
```json
{ "id": "ab12...", "title": "Backend Engineer",
  "parsed": { "role": "...", "seniority": "Senior", "min_years": 5,
              "must_have": ["Python","FastAPI"], "hard_skills": [...], ... },
  "confidence": { "role": 0.95, ... } }
```

---

## Screening

### `POST /api/screen`  (multipart)
Start an async screening run.
- `jd_id` (string, from `/api/jd`)
- `files` (repeated; PDF/DOCX/TXT CVs)

**Response:** `{ "job_id": "...", "total": 25 }`

### `GET /api/jobs/{job_id}` → `JobStatus`
Poll progress.
```json
{ "status": "parsing|ranking|explaining|done|failed", "progress": 70,
  "total": 25, "processed": 25, "elapsed_seconds": 31.2, "using_ai": true }
```

### `GET /api/results/{job_id}` → `ResultsResponse`
Ranked candidates + diversity report (available once status is `done`).

### `GET /api/candidates/{candidate_id}` → `CandidateDetail`
Full breakdown: scores, explanation (summary/strengths/gaps/flags/recommendation),
matched & missing skills, parsed CV, and tailored interview questions.

---

## Copilot, compare, export

| Endpoint | Body / params | Returns |
|----------|---------------|---------|
| `POST /api/chat` | `{ job_id, message }` | `{ response }` |
| `POST /api/compare` | `{ job_id, candidate_ids[] }` | `CandidateDetail[]` |
| `GET /api/export/csv/{job_id}` | — | CSV shortlist |
| `GET /api/export/pdf/{candidate_id}` | — | candidate PDF |
