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
from app.services.vector_store import vector_store
from app.services.diversity_service import generate_diversity_report
from app.schemas import ParsedJD, ParsedCV


async def _build_cv_text(cv: ParsedCV) -> str:
    parts = [
        cv.name,
        "Skills: " + ", ".join(cv.skills),
        "Experience: " + str(cv.years_of_experience) + " years",
        "Companies: " + ", ".join(cv.companies),
        "Education: " + str(cv.education),
        "Projects: " + str(cv.projects),
        "Achievements: " + ", ".join(cv.achievements),
    ]
    return "\n".join(parts)


async def _build_jd_text(jd: ParsedJD) -> str:
    parts = [
        f"Role: {jd.role}",
        f"Seniority: {jd.seniority}",
        f"Experience: {jd.experience_required}",
        "Hard Skills: " + ", ".join(jd.hard_skills),
        "Must Have: " + ", ".join(jd.must_have),
        "Nice To Have: " + ", ".join(jd.nice_to_have),
        "Domain: " + ", ".join(jd.domain_knowledge),
    ]
    return "\n".join(parts)


async def rank_candidates(db: AsyncSession, job_description_id: UUID, processing_job_id: UUID | None = None) -> list[Candidate]:
    jd_result = await db.execute(select(JobDescription).where(JobDescription.id == job_description_id))
    jd_record = jd_result.scalar_one_or_none()
    if not jd_record:
        raise ValueError("Job description not found")

    parsed_jd = ParsedJD(**jd_record.parsed_data) if jd_record.parsed_data else ParsedJD()
    jd_text = await _build_jd_text(parsed_jd)
    jd_embedding = await ai_service.get_embedding(jd_text)
    vector_store.upsert_jd(str(job_description_id), jd_embedding, {"role": parsed_jd.role})

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

    scored = []
    for idx, candidate in enumerate(candidates):
        parsed_cv = ParsedCV(**candidate.parsed_data) if candidate.parsed_data else ParsedCV(name=candidate.name)
        cv_text = await _build_cv_text(parsed_cv)
        cv_embedding = await ai_service.get_embedding(cv_text)
        vector_store.upsert_cv(str(candidate.id), cv_embedding, {"name": candidate.name})

        # Person 3: semantic ranking via per-dimension embedding similarity
        # (not keyword matching). See semantic_ranking.SemanticRanker.
        scores = await semantic_ranker.score_candidate(parsed_jd, parsed_cv)
        explanation = await ai_service.generate_explanation(parsed_jd, parsed_cv, scores)

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

        scored.append((candidate, scores.overall_score))

        if processing_job_id and job:
            job.progress = idx + 1
            job.message = f"Ranked {idx + 1}/{total} candidates"
            await db.flush()
            await asyncio.sleep(0.01)

    scored.sort(key=lambda x: x[1], reverse=True)
    for rank, (candidate, _) in enumerate(scored, 1):
        candidate.rank = rank
        candidate.status = "ranked"

    await generate_diversity_report(db, job_description_id)

    # Auto-generate interview questions for shortlisted top 10
    shortlisted = [c for c, _ in scored[:10]]
    for idx, candidate in enumerate(shortlisted):
        try:
            await generate_questions_for_candidate(db, candidate.id)
        except Exception:
            pass
        if processing_job_id and job:
            job.message = f"Generated questions for {idx + 1}/{len(shortlisted)} shortlisted candidates"
            await db.flush()

    if processing_job_id and job:
        job.status = ProcessingStatus.COMPLETED.value
        job.progress = total
        job.message = f"Successfully ranked {total} candidates and generated interview questions for top 10"
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
