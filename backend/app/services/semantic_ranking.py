"""
Person 3 — Semantic Ranking.

The core idea: we DO NOT keyword-match (`if "Python" in cv`). A keyword ATS
misses a candidate who wrote "Built recommendation systems" for a JD asking for
"Machine Learning". Instead we embed each dimension of the JD and the CV and
compare them with cosine similarity, so semantically related phrases score high
even when the exact words differ.

Final score (Person 3 spec):

    overall = 0.4 * skills
            + 0.3 * experience
            + 0.2 * domain
            + 0.1 * education
"""

import re

from app.services.ai_service import ai_service, cosine_similarity
from app.schemas import ParsedJD, ParsedCV, ScoreBreakdown


# Person 3's weighting of the four scoring dimensions.
WEIGHTS = {
    "skills": 0.40,
    "experience": 0.30,
    "domain": 0.20,
    "education": 0.10,
}

# Dimensions that are scored purely by embedding similarity.
SEMANTIC_DIMENSIONS = ("skills", "domain", "education")


def _norm(similarity: float) -> float:
    """Map a cosine similarity from [-1, 1] into a [0, 1] score."""
    return max(0.0, min(1.0, (similarity + 1.0) / 2.0))


def _join(*parts) -> str:
    """Flatten strings / lists / dicts into a single text blob for embedding."""
    chunks: list[str] = []
    for part in parts:
        if not part:
            continue
        if isinstance(part, str):
            chunks.append(part)
        elif isinstance(part, dict):
            chunks.append(" ".join(str(v) for v in part.values() if v))
        elif isinstance(part, (list, tuple)):
            chunks.append(_join(*part))
        else:
            chunks.append(str(part))
    return " ".join(c for c in chunks if c.strip())


def _required_years(jd: ParsedJD) -> float:
    match = re.search(r"(\d+)", jd.experience_required or "")
    return float(match.group(1)) if match else 3.0


def _jd_dimension_texts(jd: ParsedJD) -> dict[str, str]:
    """Representative text for each JD dimension."""
    return {
        "skills": _join(jd.must_have, jd.hard_skills, jd.nice_to_have, jd.role),
        "experience": _join(jd.role, jd.seniority, jd.experience_required, jd.must_have),
        "domain": _join(jd.domain_knowledge, jd.role, jd.seniority),
        "education": _join(jd.education_requirements),
    }


def _cv_dimension_texts(cv: ParsedCV) -> dict[str, str]:
    """Representative text for each CV dimension.

    Note skills pulls in projects + achievements: that is what lets
    "Built recommendation systems" match a JD skill of "Machine Learning".
    """
    return {
        "skills": _join(cv.skills, cv.projects, cv.achievements),
        "experience": _join(cv.tenure_history, cv.companies, cv.projects,
                            f"{cv.years_of_experience:g} years"),
        "domain": _join(cv.companies, cv.projects, cv.achievements),
        "education": _join(cv.education, cv.certifications),
    }


class SemanticRanker:
    async def score_candidate(self, jd: ParsedJD, cv: ParsedCV) -> ScoreBreakdown:
        jd_texts = _jd_dimension_texts(jd)
        cv_texts = _cv_dimension_texts(cv)

        # Batch-embed every dimension for both sides (2 embedding calls total).
        keys = list(WEIGHTS.keys())
        jd_embeddings = await ai_service.get_embeddings([jd_texts[k] or jd.role for k in keys])
        cv_embeddings = await ai_service.get_embeddings([cv_texts[k] or cv.name for k in keys])
        jd_emb = dict(zip(keys, jd_embeddings))
        cv_emb = dict(zip(keys, cv_embeddings))

        # Pure embedding-similarity dimensions.
        sem_scores = {
            dim: _norm(cosine_similarity(jd_emb[dim], cv_emb[dim]))
            for dim in SEMANTIC_DIMENSIONS
        }

        # Experience blends semantic role/seniority fit with the years ratio,
        # since "how senior" is partly numeric and partly contextual.
        semantic_exp = _norm(cosine_similarity(jd_emb["experience"], cv_emb["experience"]))
        required = _required_years(jd)
        years_ratio = min(1.0, cv.years_of_experience / required) if required else 1.0
        experience_score = 0.5 * semantic_exp + 0.5 * years_ratio

        skills = sem_scores["skills"]
        domain = sem_scores["domain"]
        education = sem_scores["education"]

        overall = (
            WEIGHTS["skills"] * skills
            + WEIGHTS["experience"] * experience_score
            + WEIGHTS["domain"] * domain
            + WEIGHTS["education"] * education
        ) * 100

        # Soft skills (not part of the weighted overall) scored semantically too.
        soft_score = skills
        if jd.soft_skills:
            jd_soft, cv_soft = await ai_service.get_embeddings(
                [_join(jd.soft_skills), _join(cv.achievements, cv.skills, cv.projects)]
            )
            soft_score = _norm(cosine_similarity(jd_soft, cv_soft))

        return ScoreBreakdown(
            overall_score=round(overall, 1),
            skill_score=round(skills * 100, 1),
            experience_score=round(experience_score * 100, 1),
            domain_score=round(domain * 100, 1),
            education_score=round(education * 100, 1),
            soft_skill_score=round(soft_score * 100, 1),
        )


semantic_ranker = SemanticRanker()
