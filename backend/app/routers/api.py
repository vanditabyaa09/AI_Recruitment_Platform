from __future__ import annotations
import asyncio
import csv
import io
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import AsyncSessionLocal, get_db
from app.models import JobDescription, Candidate, ProcessingJob, ProcessingStatus, ChatHistory, CandidateSkill
from app.schemas import (
    JDResponse, CandidateListItem, CandidateDetail, ProcessingJobResponse,
    AnalyticsResponse, ChatRequest, ChatResponse, RankRequest,
    GenerateQuestionsRequest, GenerateReportRequest, CompareRequest,
    ScoreBreakdown, Explanation,
)
from app.services.document_parser import save_upload, extract_text_from_bytes, validate_file_extension, validate_upload_size
from app.services.ai_service import ai_service
from app.services.ranking_service import rank_candidates, save_parsed_candidate, generate_questions_for_candidate
from app.services.analytics_service import get_analytics
from app.services.report_service import generate_candidate_pdf, generate_pool_pdf
from app.services.vector_store import vector_store

router = APIRouter()


async def _process_cvs_background(job_id: UUID, jd_id: UUID, files_data: list[tuple[bytes, str]]):
    async with AsyncSessionLocal() as db:
        try:
            job = await db.get(ProcessingJob, job_id)
            if job:
                job.status = ProcessingStatus.PROCESSING.value
                job.total_items = len(files_data)
                await db.commit()

            for idx, (content, filename) in enumerate(files_data):
                try:
                    validate_file_extension(filename)
                    file_path = await save_upload(content, filename)
                    raw_text = extract_text_from_bytes(content, filename)
                    if not raw_text.strip():
                        raw_text = f"Resume file: {filename}"
                    parsed = await ai_service.parse_cv(raw_text)
                    await save_parsed_candidate(db, jd_id, raw_text, file_path, parsed)
                except Exception as e:
                    parsed_fallback = await ai_service.parse_cv(f"Failed to parse {filename}: {e}")
                    await save_parsed_candidate(db, jd_id, "", None, parsed_fallback)

                if job:
                    job.progress = idx + 1
                    job.message = f"Processed {idx + 1}/{len(files_data)} CVs"
                    await db.commit()

            if job:
                job.status = ProcessingStatus.COMPLETED.value
                job.message = f"Successfully processed {len(files_data)} CVs"
                await db.commit()
        except Exception as e:
            job = await db.get(ProcessingJob, job_id)
            if job:
                job.status = ProcessingStatus.FAILED.value
                job.message = str(e)
                await db.commit()


@router.post("/upload-jd", response_model=JDResponse)
async def upload_jd(
    file: UploadFile | None = File(None),
    text: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    raw_text = ""
    file_path = None

    if file and file.filename:
        try:
            validate_file_extension(file.filename)
            content = await file.read()
            validate_upload_size(content, file.filename)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        file_path = await save_upload(content, file.filename)
        raw_text = extract_text_from_bytes(content, file.filename)
    elif text:
        raw_text = text
    else:
        raise HTTPException(400, "Provide a file or text input")

    if not raw_text.strip():
        raise HTTPException(400, "Could not extract text from job description")

    parsed, confidence = await ai_service.parse_job_description(raw_text)
    jd = JobDescription(
        title=parsed.role or "Untitled Role",
        raw_text=raw_text,
        file_path=file_path,
        parsed_data=parsed.model_dump(),
        confidence_scores=confidence,
    )
    db.add(jd)
    await db.flush()

    jd_text = f"Role: {parsed.role} Skills: {', '.join(parsed.hard_skills)}"
    embedding = await ai_service.get_embedding(jd_text)
    vector_store.upsert_jd(str(jd.id), embedding, {"role": parsed.role})

    return jd


@router.post("/upload-cvs")
async def upload_cvs(
    background_tasks: BackgroundTasks,
    job_description_id: UUID = Form(...),
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    jd = await db.get(JobDescription, job_description_id)
    if not jd:
        raise HTTPException(404, "Job description not found")

    if not files:
        raise HTTPException(400, "No files provided")

    files_data = []
    for f in files:
        content = await f.read()
        filename = f.filename or "resume.pdf"
        try:
            validate_file_extension(filename)
            validate_upload_size(content, filename)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        files_data.append((content, filename))

    job = ProcessingJob(
        job_description_id=job_description_id,
        job_type="cv_upload",
        status=ProcessingStatus.PENDING.value,
        total_items=len(files_data),
        message="Queued for processing",
    )
    db.add(job)
    await db.flush()
    await db.commit()

    background_tasks.add_task(_process_cvs_background, job.id, job_description_id, files_data)

    return {"job_id": str(job.id), "message": f"Processing {len(files_data)} CVs", "total": len(files_data)}


@router.get("/processing/{job_id}", response_model=ProcessingJobResponse)
async def get_processing_status(job_id: UUID, db: AsyncSession = Depends(get_db)):
    job = await db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(404, "Processing job not found")
    return job


@router.post("/rank-candidates")
async def rank_candidates_endpoint(
    request: RankRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    jd = await db.get(JobDescription, request.job_description_id)
    if not jd:
        raise HTTPException(404, "Job description not found")

    job = ProcessingJob(
        job_description_id=request.job_description_id,
        job_type="ranking",
        status=ProcessingStatus.PENDING.value,
        message="Queued for ranking",
    )
    db.add(job)
    await db.flush()
    job_id = job.id
    await db.commit()

    async def _rank_task():
        async with AsyncSessionLocal() as session:
            await rank_candidates(session, request.job_description_id, job_id)
            await session.commit()

    background_tasks.add_task(_rank_task)
    return {"job_id": str(job.id), "message": "Ranking started"}


@router.get("/candidates")
async def list_candidates(
    job_description_id: UUID | None = None,
    search: str | None = None,
    min_score: float | None = None,
    min_experience: float | None = None,
    max_experience: float | None = None,
    required_skills: str | None = None,
    hidden_gems_only: bool = False,
    sort_by: str = "rank",
    sort_order: str = "asc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(Candidate).options(selectinload(Candidate.scores), selectinload(Candidate.skills))
    if job_description_id:
        query = query.where(Candidate.job_description_id == job_description_id)
    if search:
        query = query.where(or_(Candidate.name.ilike(f"%{search}%"), Candidate.email.ilike(f"%{search}%")))
    if hidden_gems_only:
        query = query.where(Candidate.is_hidden_gem == True)
    if min_experience is not None:
        query = query.where(Candidate.years_of_experience >= min_experience)
    if max_experience is not None:
        query = query.where(Candidate.years_of_experience <= max_experience)
    if required_skills:
        skills_list = [s.strip() for s in required_skills.split(",") if s.strip()]
        for skill in skills_list:
            query = query.where(Candidate.skills.any(CandidateSkill.skill_name.ilike(f"%{skill}%")))

    result = await db.execute(query)
    candidates = list(result.scalars().all())

    if min_score is not None:
        candidates = [c for c in candidates if c.scores and c.scores.overall_score >= min_score]

    reverse = sort_order == "desc"
    if sort_by == "score":
        candidates.sort(key=lambda c: c.scores.overall_score if c.scores else 0, reverse=reverse)
    elif sort_by == "name":
        candidates.sort(key=lambda c: c.name, reverse=reverse)
    elif sort_by == "experience":
        candidates.sort(key=lambda c: c.years_of_experience, reverse=reverse)
    else:
        candidates.sort(key=lambda c: c.rank or 9999, reverse=not reverse if sort_by == "rank" else reverse)

    total = len(candidates)
    start = (page - 1) * page_size
    page_items = candidates[start : start + page_size]

    items = []
    for c in page_items:
        items.append(CandidateListItem(
            id=c.id,
            rank=c.rank,
            name=c.name,
            overall_score=c.scores.overall_score if c.scores else 0,
            years_of_experience=c.years_of_experience,
            top_skills=[s.skill_name for s in c.skills[:5]],
            status=c.status,
            is_hidden_gem=c.is_hidden_gem,
        ))

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/candidate/{candidate_id}", response_model=CandidateDetail)
async def get_candidate(candidate_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Candidate)
        .where(Candidate.id == candidate_id)
        .options(
            selectinload(Candidate.scores),
            selectinload(Candidate.skills),
            selectinload(Candidate.experiences),
            selectinload(Candidate.interview_questions),
        )
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Candidate not found")

    scores = None
    explanation = None
    exec_summary = None
    if c.scores:
        scores = ScoreBreakdown(
            overall_score=c.scores.overall_score,
            skill_score=c.scores.skill_score,
            experience_score=c.scores.experience_score,
            domain_score=c.scores.domain_score,
            education_score=c.scores.education_score,
            soft_skill_score=c.scores.soft_skill_score,
        )
        if c.scores.explanation:
            explanation = Explanation(**c.scores.explanation)
        exec_summary = c.scores.executive_summary

    return CandidateDetail(
        id=c.id,
        name=c.name,
        email=c.email,
        phone=c.phone,
        location=c.location,
        parsed_data=c.parsed_data,
        years_of_experience=c.years_of_experience,
        rank=c.rank,
        is_hidden_gem=c.is_hidden_gem,
        scores=scores,
        explanation=explanation,
        executive_summary=exec_summary,
        skills=[s.skill_name for s in c.skills],
        experiences=[{"company": e.company, "role": e.role, "start": e.start_date, "end": e.end_date} for e in c.experiences],
        interview_questions=[{"category": q.category, "question": q.question} for q in c.interview_questions],
    )


@router.get("/analytics", response_model=AnalyticsResponse)
async def analytics(
    job_description_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await get_analytics(db, job_description_id)


@router.post("/generate-questions")
async def generate_questions(request: GenerateQuestionsRequest, db: AsyncSession = Depends(get_db)):
    questions = await generate_questions_for_candidate(db, request.candidate_id)
    return {"questions": [{"category": q.category, "question": q.question} for q in questions]}


@router.post("/generate-report")
async def generate_report(request: GenerateReportRequest, db: AsyncSession = Depends(get_db)):
    pdf_bytes = await generate_candidate_pdf(db, request.candidate_id)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=candidate_report.pdf"},
    )


@router.get("/export/csv")
async def export_csv(
    job_description_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Candidate).options(selectinload(Candidate.scores), selectinload(Candidate.skills))
    if job_description_id:
        query = query.where(Candidate.job_description_id == job_description_id)
    result = await db.execute(query)
    candidates = list(result.scalars().all())
    candidates.sort(key=lambda c: c.rank or 9999)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Rank", "Name", "Score", "Experience", "Top Skills", "Status", "Hidden Gem"])
    for c in candidates:
        writer.writerow([
            c.rank or "",
            c.name,
            c.scores.overall_score if c.scores else 0,
            c.years_of_experience,
            ", ".join(s.skill_name for s in c.skills[:5]),
            c.status,
            "Yes" if c.is_hidden_gem else "No",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=candidates.csv"},
    )


@router.get("/export/pdf")
async def export_pdf(
    job_description_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    pdf_bytes = await generate_pool_pdf(db, job_description_id)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=candidates_report.pdf"},
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    context_parts = []
    if request.job_description_id:
        result = await db.execute(
            select(Candidate)
            .where(Candidate.job_description_id == request.job_description_id)
            .options(selectinload(Candidate.scores), selectinload(Candidate.skills))
            .limit(50)
        )
        candidates = list(result.scalars().all())
        for c in sorted(candidates, key=lambda x: x.rank or 999)[:20]:
            score = c.scores.overall_score if c.scores else 0
            skills = ", ".join(s.skill_name for s in c.skills[:8])
            context_parts.append(f"#{c.rank or '-'} {c.name} (score: {score}, skills: {skills}, hidden_gem: {c.is_hidden_gem})")

    context = "\n".join(context_parts) or "No candidate data available."
    response = await ai_service.chat_response(request.message, context)

    db.add(ChatHistory(
        job_description_id=request.job_description_id,
        session_id=request.session_id,
        role="user",
        content=request.message,
    ))
    db.add(ChatHistory(
        job_description_id=request.job_description_id,
        session_id=request.session_id,
        role="assistant",
        content=response,
    ))

    return ChatResponse(response=response, session_id=request.session_id)


@router.post("/compare")
async def compare_candidates(request: CompareRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Candidate)
        .where(Candidate.id.in_(request.candidate_ids))
        .options(selectinload(Candidate.scores), selectinload(Candidate.skills))
    )
    candidates = list(result.scalars().all())
    comparison = []
    for c in candidates:
        comparison.append({
            "id": str(c.id),
            "name": c.name,
            "rank": c.rank,
            "scores": {
                "overall": c.scores.overall_score if c.scores else 0,
                "skill": c.scores.skill_score if c.scores else 0,
                "experience": c.scores.experience_score if c.scores else 0,
            } if c.scores else {},
            "skills": [s.skill_name for s in c.skills[:10]],
            "years_of_experience": c.years_of_experience,
            "is_hidden_gem": c.is_hidden_gem,
        })
    comparison.sort(key=lambda x: x["rank"] or 999)
    return {"candidates": comparison}


@router.get("/job-descriptions")
async def list_job_descriptions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(JobDescription).order_by(JobDescription.created_at.desc()))
    jds = list(result.scalars().all())
    return [{"id": str(jd.id), "title": jd.title, "created_at": jd.created_at.isoformat()} for jd in jds]


@router.get("/job-description/{jd_id}")
async def get_job_description(jd_id: UUID, db: AsyncSession = Depends(get_db)):
    jd = await db.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(404, "Job description not found")
    return JDResponse(
        id=jd.id,
        title=jd.title,
        parsed_data=jd.parsed_data,
        confidence_scores=jd.confidence_scores,
        created_at=jd.created_at,
    )


@router.post("/hiring-recommendation")
async def hiring_recommendation(job_description_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Candidate)
        .where(Candidate.job_description_id == job_description_id)
        .options(selectinload(Candidate.scores), selectinload(Candidate.skills))
    )
    candidates = list(result.scalars().all())
    ranked = sorted([c for c in candidates if c.scores], key=lambda c: c.scores.overall_score, reverse=True)

    top = ranked[:3]
    gems = [c for c in ranked if c.is_hidden_gem][:2]

    recommendation = {
        "summary": f"Based on analysis of {len(candidates)} candidates, we recommend proceeding with technical interviews for the top-ranked candidates.",
        "primary_recommendations": [
            {
                "name": c.name,
                "score": c.scores.overall_score,
                "rank": c.rank,
                "rationale": c.scores.executive_summary or f"Strong match with {c.scores.overall_score:.0f}% overall score",
            }
            for c in top
        ],
        "hidden_gems_to_consider": [
            {"name": c.name, "score": c.scores.overall_score, "rank": c.rank}
            for c in gems
        ],
        "next_steps": [
            "Schedule technical interviews with top 3 candidates",
            "Review hidden gems for diverse pipeline",
            "Use generated interview questions for structured assessment",
        ],
    }
    return recommendation
