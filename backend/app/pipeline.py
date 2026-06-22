"""Screening pipeline orchestration.

Performance strategy (the assignment requires 20+ CVs in <60s on a rate-limited
free tier):
  1. Parse CVs in BATCHES (many CVs per LLM call) with capped concurrency.
  2. Embed the JD + all CVs in one batched embedding call.
  3. Score & rank locally (no API).
  4. Generate full explanations + tailored questions only for the shortlist,
     concurrently (semaphore-bounded, with 429 backoff in the client).
The rest of the pool gets instant deterministic explanations.
"""
from __future__ import annotations

import time
import asyncio
import logging

from app.config import get_settings
from app import ai, ranking, diversity
from app.store import store, Candidate, ScreeningJob

logger = logging.getLogger("recruitiq.pipeline")
settings = get_settings()


def _jd_embed_text(jd) -> str:
    p = jd.parsed
    return (f"{p.role}. {p.seniority}. Skills: {', '.join(p.hard_skills)}. "
            f"Must have: {', '.join(p.must_have)}. Domain: {', '.join(p.domain_knowledge)}. "
            f"Responsibilities: {' '.join(p.responsibilities)}")[:8000]


def _cv_embed_text(cv) -> str:
    return (f"{cv.headline}. Skills: {', '.join(cv.skills)}. "
            f"Experience: {' '.join(x.role + ' at ' + x.company for x in cv.experience)}. "
            f"Achievements: {' '.join(cv.achievements)}")[:8000]


async def run_screening(job: ScreeningJob, raw_cvs: list[tuple[str, str]]) -> None:
    """raw_cvs: list of (filename, raw_text). Mutates job + store in place."""
    job.started_at = time.monotonic()
    job.using_ai = ai.gemini.available
    try:
        jd = store.get_jd(job.jd_id)
        if not jd:
            raise RuntimeError("Job description not found")

        # ---- 1. Parse CVs in batches -------------------------------------
        job.status = "parsing"
        job.message = "Reading and structuring CVs"
        docs = list(enumerate(raw_cvs))  # (idx, (filename, text))
        batch_size = settings.cv_parse_batch_size
        batches = [docs[i:i + batch_size] for i in range(0, len(docs), batch_size)]

        async def parse_batch(batch):
            payload = [(idx, text) for idx, (_, text) in batch]
            return await ai.parse_cv_batch(payload)

        parsed_maps = await asyncio.gather(*(parse_batch(b) for b in batches))
        parsed: dict[int, object] = {}
        for m in parsed_maps:
            parsed.update(m)
        job.processed = len(parsed)
        job.progress = 45

        # Build candidate records
        candidates: list[Candidate] = []
        from app.store import new_id
        for idx, (filename, text) in docs:
            cv = parsed.get(idx) or ai._heuristic_cv(text)
            c = Candidate(id=new_id(), job_id=job.id, filename=filename,
                          raw_text=text, parsed=cv)
            store.add_candidate(c)
            candidates.append(c)
        job.candidate_ids = [c.id for c in candidates]

        # ---- 2. Embeddings (one batched call) ----------------------------
        job.status = "ranking"
        job.message = "Scoring semantic fit"
        texts = [_jd_embed_text(jd)] + [_cv_embed_text(c.parsed) for c in candidates]
        embeddings = await ai.gemini.embed(texts)
        jd.embedding = embeddings[0]
        for c, emb in zip(candidates, embeddings[1:]):
            c.embedding = emb
        job.progress = 60

        # ---- 3. Score & rank (local) -------------------------------------
        for c in candidates:
            sem = ranking.cosine_similarity(jd.embedding, c.embedding)
            scores, matched, missing = ranking.compute_scores(jd.parsed, c.parsed, sem)
            c.scores = scores
            c.matched_skills = matched
            c.missing_skills = missing
        candidates.sort(key=lambda c: c.scores.overall, reverse=True)
        for rank, c in enumerate(candidates, start=1):
            c.rank = rank
        job.progress = 70

        # ---- 4. Diversity / hidden gems ----------------------------------
        div = diversity.analyze(candidates, settings.shortlist_size)
        job.diversity = div

        # ---- 5. Explanations for the shortlist ---------------------------
        # Interview questions are NOT generated here — recruiters generate them
        # on demand per candidate (saves quota; see the /questions endpoint).
        job.status = "explaining"
        job.message = "Writing fit explanations"
        shortlist = candidates[:settings.shortlist_size]
        # Include hidden gems so recruiters get their rationale too.
        gem_ids = set(div["hidden_gem_ids"])
        to_explain = shortlist + [c for c in candidates if c.id in gem_ids and c not in shortlist]

        # Batch candidates per LLM call to stay within rate limits (a 20-CV run
        # ends up ~7 generate calls total: 1 JD + ~3 parse + ~2 explain).
        bsize = settings.explain_batch_size
        ex_batches = [to_explain[i:i + bsize] for i in range(0, len(to_explain), bsize)]
        done = {"n": 0}
        total_b = max(len(ex_batches), 1)
        by_id = {c.id: c for c in to_explain}

        async def explain_batch(batch: list[Candidate]):
            items = [(c.id, c.parsed, c.scores) for c in batch]
            results = await ai.explain_candidates_batch(jd.parsed, items)
            for cid, expl in results.items():
                cand = by_id.get(cid)
                if cand:
                    cand.explanation = expl
            done["n"] += 1
            job.progress = 70 + int(28 * done["n"] / total_b)

        await asyncio.gather(*(explain_batch(b) for b in ex_batches))

        # Everyone else gets an instant heuristic explanation.
        for c in candidates:
            if c.explanation is None:
                c.explanation = ai._heuristic_explanation(jd.parsed, c.parsed, c.scores)

        job.status = "done"
        job.progress = 100
        job.processed = len(candidates)
        job.finished_at = time.monotonic()
        job.message = f"Screened {len(candidates)} candidates"
        logger.info("Screening %s done: %d CVs in %.1fs (AI=%s)",
                    job.id, len(candidates), job.finished_at - job.started_at, job.using_ai)
    except Exception as e:
        logger.exception("Screening job %s failed", job.id)
        job.status = "failed"
        job.error = str(e)
        job.message = f"Screening failed: {e}"
        job.finished_at = time.monotonic()
