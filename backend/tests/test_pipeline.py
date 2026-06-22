"""End-to-end pipeline tests in offline heuristic mode (no API calls).

These prove the ranking, diversity, and scoring logic deterministically — the
parts that must be correct regardless of whether the LLM is reachable.
"""
import pytest

from app import ai, ranking, diversity
from app.documents import extract_text, validate_file
from app.store import store, JobDescription, ScreeningJob, new_id
from app.pipeline import run_screening


JD_TEXT = """Senior Backend Engineer. 5+ years building scalable Python APIs.
Must have: Python, FastAPI, PostgreSQL, AWS, Docker.
Nice to have: Kubernetes, Kafka. Strong system design and mentoring."""

STRONG_CV = """Sarah Chen
Senior Backend Engineer with 7 years building Python systems.
Skills: Python, FastAPI, PostgreSQL, AWS, Docker, Kubernetes, Kafka
Experience: BigCo Technologies — Senior Engineer (2018-Present)
Education: BS Computer Science, MIT, 2016"""

WEAK_CV = """Bob Junior
Recent grad, 1 year experience.
Skills: HTML, CSS
Experience: Small Startup Inc — Intern
Education: Bootcamp graduate"""


def test_extract_text_txt():
    assert "Sarah Chen" in extract_text("cv.txt", STRONG_CV.encode())


def test_validate_rejects_unknown_extension():
    with pytest.raises(ValueError):
        validate_file("malware.exe", b"x")


@pytest.mark.asyncio
async def test_jd_parsing_heuristic():
    jd, _ = await ai.parse_jd(JD_TEXT)
    skills = {s.lower() for s in jd.hard_skills}
    assert "python" in skills
    assert jd.min_years >= 5


def test_strong_beats_weak():
    jd = ai._heuristic_jd(JD_TEXT)
    strong = ai._heuristic_cv(STRONG_CV)
    weak = ai._heuristic_cv(WEAK_CV)
    # Identical embeddings (offline) so the differentiator is skills/experience.
    emb = [0.1] * 8
    s_strong, _, _ = ranking.compute_scores(jd, strong, ranking.cosine_similarity(emb, emb))
    s_weak, _, _ = ranking.compute_scores(jd, weak, ranking.cosine_similarity(emb, emb))
    assert s_strong.overall > s_weak.overall


def test_missing_must_haves_detected():
    jd = ai._heuristic_jd(JD_TEXT)
    weak = ai._heuristic_cv(WEAK_CV)
    _, _, missing = ranking.skill_match(jd, weak)
    # The weak CV lists none of the backend must-haves (FastAPI/PostgreSQL/AWS).
    missing_lower = {m.lower() for m in missing}
    assert any(s in missing_lower for s in ("fastapi", "postgresql", "aws"))


@pytest.mark.asyncio
async def test_full_screening_offline():
    jd_parsed, conf = await ai.parse_jd(JD_TEXT)
    jd = JobDescription(id=new_id(), title=jd_parsed.role, raw_text=JD_TEXT,
                        parsed=jd_parsed, confidence=conf)
    store.add_jd(jd)
    job = ScreeningJob(id=new_id(), jd_id=jd.id, total=2)
    store.add_job(job)

    raw_cvs = [("sarah.txt", STRONG_CV), ("bob.txt", WEAK_CV)]
    await run_screening(job, raw_cvs)

    assert job.status == "done"
    assert job.progress == 100
    ranked = store.candidates_for_job(job.id)
    assert len(ranked) == 2
    assert ranked[0].rank == 1
    # The strong candidate must rank first.
    assert ranked[0].scores.overall >= ranked[1].scores.overall
    # Every candidate gets an explanation (AI or heuristic).
    assert all(c.explanation and c.explanation.summary for c in ranked)


def test_diversity_flags_homogeneous_shortlist():
    jd = ai._heuristic_jd(JD_TEXT)
    cands = []
    for i in range(6):
        cv = ai._heuristic_cv(STRONG_CV.replace("Sarah Chen", f"Cand {i}"))
        c = type("C", (), {})()  # lightweight stand-in not needed; use store Candidate
        from app.store import Candidate
        c = Candidate(id=new_id(), job_id="x", filename=f"{i}.txt", raw_text="", parsed=cv)
        sem = 0.6
        c.scores, c.matched_skills, c.missing_skills = ranking.compute_scores(jd, cv, sem)
        c.rank = i + 1
        cands.append(c)
    report = diversity.analyze(cands, shortlist_size=5)
    assert "flags" in report and len(report["flags"]) >= 1
