"""Semantic + structured candidate scoring.

Overall score blends a semantic embedding similarity (captures fit that keyword
matching misses) with interpretable sub-scores so the breakdown is explainable.
"""
from __future__ import annotations

import re

import numpy as np

from app.schemas import ParsedJD, ParsedCV, ScoreBreakdown

# Weights for the overall score. Semantic similarity is weighted alongside
# concrete skill matching so neither keyword-stuffing nor vague prose wins alone.
WEIGHTS = {
    "skills": 0.32,
    "semantic": 0.25,
    "experience": 0.18,
    "domain": 0.10,
    "education": 0.07,
    "soft_skills": 0.08,
}


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def _norm_skill(s: str) -> str:
    return re.sub(r"[^a-z0-9+#]", "", s.lower())


def skill_match(jd: ParsedJD, cv: ParsedCV) -> tuple[float, list[str], list[str]]:
    """Returns (score 0-1, matched must/hard skills, missing must-haves)."""
    cv_norm = {_norm_skill(s) for s in cv.skills}
    target = jd.must_have + jd.hard_skills
    if not target:
        return 0.6, [], []

    # Must-haves weigh double — they're non-negotiable.
    must = {_norm_skill(s): s for s in jd.must_have}
    hard = {_norm_skill(s): s for s in jd.hard_skills}

    matched_must = [orig for n, orig in must.items() if n in cv_norm]
    matched_hard = [orig for n, orig in hard.items() if n in cv_norm]
    missing_must = [orig for n, orig in must.items() if n not in cv_norm]

    must_total = len(must) or 1
    hard_total = len(hard) or 1
    must_ratio = len(matched_must) / must_total
    hard_ratio = len(matched_hard) / hard_total
    score = 0.65 * must_ratio + 0.35 * hard_ratio if must else hard_ratio

    matched = list(dict.fromkeys(matched_must + matched_hard))
    return min(1.0, score), matched, missing_must


def experience_score(jd: ParsedJD, cv: ParsedCV) -> float:
    required = jd.min_years or 3.0
    if required <= 0:
        return 0.8
    ratio = cv.years_of_experience / required
    # Slight bonus for meeting/exceeding, but cap so 20y doesn't dwarf everything.
    return float(min(1.0, 0.15 + 0.85 * min(ratio, 1.2) / 1.2)) if cv.years_of_experience else 0.1


def education_score(jd: ParsedJD, cv: ParsedCV) -> float:
    if not jd.education_requirements:
        return 0.75 if cv.education else 0.6
    return 0.85 if cv.education else 0.45


def soft_skill_score(jd: ParsedJD, cv: ParsedCV) -> float:
    if not jd.soft_skills:
        return 0.7
    jd_soft = {_norm_skill(s) for s in jd.soft_skills}
    blob = " ".join(cv.skills + [h for x in cv.experience for h in x.highlights] + cv.achievements).lower()
    hits = sum(1 for s in jd_soft if s and s in re.sub(r"[^a-z0-9 ]", "", blob))
    return min(1.0, 0.5 + 0.5 * hits / max(len(jd_soft), 1))


def compute_scores(jd: ParsedJD, cv: ParsedCV, semantic: float
                   ) -> tuple[ScoreBreakdown, list[str], list[str]]:
    # Map cosine [-1,1] -> [0,1]
    sem = max(0.0, min(1.0, (semantic + 1) / 2))
    skills, matched, missing = skill_match(jd, cv)
    exp = experience_score(jd, cv)
    domain = 0.5 + 0.5 * sem  # domain fit approximated by semantic proximity
    edu = education_score(jd, cv)
    soft = soft_skill_score(jd, cv)

    overall = (
        WEIGHTS["skills"] * skills
        + WEIGHTS["semantic"] * sem
        + WEIGHTS["experience"] * exp
        + WEIGHTS["domain"] * domain
        + WEIGHTS["education"] * edu
        + WEIGHTS["soft_skills"] * soft
    ) * 100

    breakdown = ScoreBreakdown(
        overall=round(overall, 1),
        skills=round(skills * 100, 1),
        semantic=round(sem * 100, 1),
        experience=round(exp * 100, 1),
        domain=round(domain * 100, 1),
        education=round(edu * 100, 1),
        soft_skills=round(soft * 100, 1),
    )
    return breakdown, matched, missing
