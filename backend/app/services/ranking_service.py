from __future__ import annotations
import asyncio
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Candidate, CandidateSkill, CandidateExperience, CandidateScore,
    InterviewQuestion, JobDescription, ProcessingJob, ProcessingStatus,
)
from app.services.ai_service import ai_service
from app.services.semantic_ranking import semantic_ranker
from app.services.diversity_service import generate_diversity_report
from app.schemas import ParsedJD, ParsedCV

# How many candidates we spend LLM tokens on (written explanation + tailored
# questions). The rest get a free, rule-based explanation. Hidden gems below
# the cut are always added so non-traditional standouts are still surfaced.
SHORTLIST_SIZE = 10
# Concurrency cap for the shortlist's network-bound LLM calls.
ANALYSIS_CONCURRENCY = 6


async def rank_candidates(db: AsyncSession, job_description_id: UUID, processing_job_id: UUID | None = None) -> list[Candidate]:
    jd_result = await db.execute(select(JobDescription).where(JobDescription.id == job_description_id))
    jd_record = jd_result.scalar_one_or_none()
    if not jd_record:
        raise ValueError("Job description not found")

    parsed_jd = ParsedJD(**jd_record.parsed_data) if jd_record.parsed_data else ParsedJD()

    result = await db.execute(
        select(Candidate)
        .where(Candidate.job_description_id == job_description_id)
        .options(selectinload(Candidate.scores))
    )
    candidates = list(result.scalars().all())
    total = len(candidates)

    if processing_job_id:
        job = await db.get(ProcessingJob, processing_job_id)
        if job:
            job.status = ProcessingStatus.PROCESSING.value
            job.total_items = total
            job.message = "Ranking candidates..."
            await db.flush()

    # 1) Score everyone. Semantic scoring (Person 3) is token-light thanks to
    #    the embedding cache (the JD's dimension embeddings are computed once and
    #    reused across all candidates). Explanations here are the free rule-based
    #    baseline; LLM-written ones are added only for the surfaced set (step 3).
    scored = []
    score_map: dict = {}
    for idx, candidate in enumerate(candidates):
        parsed_cv = ParsedCV(**candidate.parsed_data) if candidate.parsed_data else ParsedCV(name=candidate.name)

        # Person 3: semantic ranking via per-dimension embedding similarity
        # (not keyword matching). See semantic_ranking.SemanticRanker.
        scores = await semantic_ranker.score_candidate(parsed_jd, parsed_cv)
        explanation = ai_service.local_explanation(parsed_jd, parsed_cv, scores)

        if candidate.scores:
            candidate.scores.overall_score = scores.overall_score
            candidate.scores.skill_score = scores.skill_score
            candidate.scores.experience_score = scores.experience_score
            candidate.scores.domain_score = scores.domain_score
            candidate.scores.education_score = scores.education_score
            candidate.scores.soft_skill_score = scores.soft_skill_score
            candidate.scores.explanation = explanation.model_dump()
            candidate.scores.executive_summary = explanation.summary
        else:
            score_record = CandidateScore(
                candidate_id=candidate.id,
                overall_score=scores.overall_score,
                skill_score=scores.skill_score,
                experience_score=scores.experience_score,
                domain_score=scores.domain_score,
                education_score=scores.education_score,
                soft_skill_score=scores.soft_skill_score,
                explanation=explanation.model_dump(),
                executive_summary=explanation.summary,
            )
            db.add(score_record)
            candidate.scores = score_record

        score_map[candidate.id] = (parsed_cv, scores)
        scored.append((candidate, scores.overall_score))

        if processing_job_id and job:
            job.progress = idx + 1
            job.message = f"Scored {idx + 1}/{total} candidates"
            await db.flush()

    scored.sort(key=lambda x: x[1], reverse=True)
    for rank, (candidate, _) in enumerate(scored, 1):
        candidate.rank = rank
        candidate.status = "ranked"
    await db.flush()

    # 2) Diversity pass flags hidden gems — must run before we pick who to explain.
    await generate_diversity_report(db, job_description_id)

    # 3) Spend LLM tokens only on the surfaced set: top SHORTLIST_SIZE + any
    #    hidden gems below the cut. A single combined call per candidate returns
    #    both the written explanation and tailored interview questions.
    top_cut = [c for c, _ in scored[:SHORTLIST_SIZE]]
    gems = [c for c, _ in scored[SHORTLIST_SIZE:] if c.is_hidden_gem]
    shortlist = top_cut + gems

    if processing_job_id and job:
        job.message = f"Generating explanations and questions for {len(shortlist)} shortlisted candidates..."
        await db.flush()

    sem = asyncio.Semaphore(ANALYSIS_CONCURRENCY)

    async def _analyze(candidate):
        parsed_cv, score_breakdown = score_map[candidate.id]
        async with sem:
            return candidate, await ai_service.analyze_candidate(parsed_jd, parsed_cv, score_breakdown)

    # Run the network-bound LLM calls concurrently, then persist sequentially —
    # a single AsyncSession must not be used from concurrent tasks.
    analyses = await asyncio.gather(*[_analyze(c) for c in shortlist], return_exceptions=True)
    for item in analyses:
        if isinstance(item, BaseException):
            continue
        candidate, (explanation, questions) = item
        if candidate.scores:
            candidate.scores.explanation = explanation.model_dump()
            candidate.scores.executive_summary = explanation.summary

        existing = await db.execute(
            select(InterviewQuestion).where(InterviewQuestion.candidate_id == candidate.id)
        )
        for q in existing.scalars().all():
            await db.delete(q)
        for q in questions:
            db.add(InterviewQuestion(
                candidate_id=candidate.id,
                category=q.get("category", "technical"),
                question=q.get("question", ""),
            ))
    await db.flush()

    if processing_job_id and job:
        job.status = ProcessingStatus.COMPLETED.value
        job.progress = total
        job.message = f"Ranked {total} candidates; explained and prepared questions for top {len(shortlist)}"
        await db.flush()

    return [c for c, _ in scored]


async def save_parsed_candidate(
    db: AsyncSession,
    job_description_id: UUID,
    raw_text: str,
    file_path: str | None,
    parsed: ParsedCV,
) -> Candidate:
    candidate = Candidate(
        job_description_id=job_description_id,
        name=parsed.name,
        email=parsed.email,
        phone=parsed.phone,
        location=parsed.location,
        raw_text=raw_text,
        file_path=file_path,
        parsed_data=parsed.model_dump(),
        years_of_experience=parsed.years_of_experience,
        status="processed",
    )
    db.add(candidate)
    await db.flush()

    for skill in parsed.skills[:20]:
        db.add(CandidateSkill(candidate_id=candidate.id, skill_name=skill, category="technical"))

    for tenure in parsed.tenure_history[:10]:
        if isinstance(tenure, dict):
            db.add(CandidateExperience(
                candidate_id=candidate.id,
                company=tenure.get("company", "Unknown"),
                role=tenure.get("role", ""),
                start_date=tenure.get("start"),
                end_date=tenure.get("end"),
            ))

    return candidate


async def generate_questions_for_candidate(db: AsyncSession, candidate_id: UUID) -> list[InterviewQuestion]:
    result = await db.execute(
        select(Candidate)
        .where(Candidate.id == candidate_id)
        .options(selectinload(Candidate.interview_questions), selectinload(Candidate.job_description))
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise ValueError("Candidate not found")

    parsed_cv = ParsedCV(**candidate.parsed_data) if candidate.parsed_data else ParsedCV(name=candidate.name)
    parsed_jd = ParsedJD()
    if candidate.job_description and candidate.job_description.parsed_data:
        parsed_jd = ParsedJD(**candidate.job_description.parsed_data)

    questions_data = await ai_service.generate_interview_questions(parsed_jd, parsed_cv)

    for q in candidate.interview_questions:
        await db.delete(q)
    await db.flush()

    questions = []
    for q in questions_data:
        iq = InterviewQuestion(
            candidate_id=candidate_id,
            category=q.get("category", "technical"),
            question=q.get("question", ""),
        )
        db.add(iq)
        questions.append(iq)

    await db.flush()
    return questions
