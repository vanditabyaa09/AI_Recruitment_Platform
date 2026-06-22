"""REST API. Flow:
  POST /jd            -> parse a job description
  POST /screen        -> upload CVs, kick off async screening, returns job_id
  GET  /jobs/{id}     -> poll screening progress
  GET  /results/{id}  -> ranked candidates + diversity report
  GET  /candidates/{id} -> full candidate detail (scores, explanation, questions)
  POST /chat          -> recruiter copilot
  POST /compare       -> side-by-side candidate comparison
  GET  /export/...    -> CSV / PDF
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse

from app import ai, report
from app.config import get_settings
from app.documents import validate_file, extract_text
from app.pipeline import run_screening
from app.store import store, JobDescription, ScreeningJob, new_id
from app.schemas import (
    JDTextRequest, JDResponse, JobStatus, ResultsResponse, CandidateSummary,
    CandidateDetail, DiversityReport, DiversityFlag, ChatRequest, ChatResponse,
    CompareRequest,
)

logger = logging.getLogger("recruitiq.api")
settings = get_settings()
router = APIRouter()


# --------------------------------------------------------------------------
# Job description
# --------------------------------------------------------------------------
@router.post("/jd", response_model=JDResponse)
async def upload_jd(
    file: UploadFile | None = File(None),
    text: str | None = Form(None),
):
    raw = ""
    if file and file.filename:
        content = await file.read()
        try:
            validate_file(file.filename, content)
        except ValueError as e:
            raise HTTPException(400, str(e))
        raw = extract_text(file.filename, content)
    elif text:
        raw = text
    else:
        raise HTTPException(400, "Provide a job description file or text.")

    if not raw.strip():
        raise HTTPException(400, "Could not extract any text from the job description.")

    parsed, confidence = await ai.parse_jd(raw)
    jd = JobDescription(
        id=new_id(),
        title=parsed.role or "Untitled Role",
        raw_text=raw,
        parsed=parsed,
        confidence=confidence,
    )
    store.add_jd(jd)
    return JDResponse(id=jd.id, title=jd.title, parsed=parsed, confidence=confidence)


@router.post("/jd/text", response_model=JDResponse)
async def upload_jd_text(body: JDTextRequest):
    if not body.text.strip():
        raise HTTPException(400, "Job description text is empty.")
    parsed, confidence = await ai.parse_jd(body.text)
    jd = JobDescription(id=new_id(), title=parsed.role or "Untitled Role",
                        raw_text=body.text, parsed=parsed, confidence=confidence)
    store.add_jd(jd)
    return JDResponse(id=jd.id, title=jd.title, parsed=parsed, confidence=confidence)


# --------------------------------------------------------------------------
# Screening
# --------------------------------------------------------------------------
@router.post("/screen")
async def screen(
    background_tasks: BackgroundTasks,
    jd_id: str = Form(...),
    files: list[UploadFile] = File(...),
):
    jd = store.get_jd(jd_id)
    if not jd:
        raise HTTPException(404, "Job description not found. Upload a JD first.")
    if not files:
        raise HTTPException(400, "No CV files provided.")

    raw_cvs: list[tuple[str, str]] = []
    for f in files:
        content = await f.read()
        name = f.filename or "cv.txt"
        try:
            validate_file(name, content)
        except ValueError as e:
            raise HTTPException(400, str(e))
        raw_cvs.append((name, extract_text(name, content)))

    job = ScreeningJob(id=new_id(), jd_id=jd_id, status="pending",
                       total=len(raw_cvs), message="Queued")
    store.add_job(job)
    background_tasks.add_task(_run, job, raw_cvs)
    return {"job_id": job.id, "total": len(raw_cvs)}


async def _run(job: ScreeningJob, raw_cvs):
    await run_screening(job, raw_cvs)


@router.get("/jobs/{job_id}", response_model=JobStatus)
async def job_status(job_id: str):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404, "Screening job not found.")
    import time
    elapsed = (job.finished_at or time.monotonic()) - job.started_at if job.started_at else 0.0
    return JobStatus(
        id=job.id, jd_id=job.jd_id, status=job.status, progress=job.progress,
        total=job.total, processed=job.processed, message=job.message,
        elapsed_seconds=round(elapsed, 1), using_ai=job.using_ai,
    )


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------
@router.get("/results/{job_id}", response_model=ResultsResponse)
async def results(job_id: str):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404, "Screening job not found.")
    if job.status != "done":
        raise HTTPException(409, f"Screening not finished (status: {job.status}).")
    jd = store.get_jd(job.jd_id)
    candidates = store.candidates_for_job(job_id)

    summaries = [_summary(c) for c in candidates]
    div = job.diversity or {}
    gem_ids = set(div.get("hidden_gem_ids", []))
    report_obj = DiversityReport(
        skewed=div.get("skewed", False),
        flags=[DiversityFlag(**f) for f in div.get("flags", [])],
        hidden_gems=[_summary(c) for c in candidates if c.id in gem_ids],
        shortlist_size=div.get("shortlist_size", 0),
        distribution=div.get("distribution", {}),
    )
    elapsed = (job.finished_at - job.started_at) if job.started_at else 0.0
    return ResultsResponse(
        job_id=job.id,
        jd=JDResponse(id=jd.id, title=jd.title, parsed=jd.parsed, confidence=jd.confidence),
        candidates=summaries,
        diversity=report_obj,
        using_ai=job.using_ai,
        elapsed_seconds=round(elapsed, 1),
    )


@router.get("/candidates/{candidate_id}", response_model=CandidateDetail)
async def candidate_detail(candidate_id: str):
    c = store.get_candidate(candidate_id)
    if not c:
        raise HTTPException(404, "Candidate not found.")
    if not c.interview_questions and c.scores:
        # Lazily generate questions for non-shortlisted candidates on demand.
        jd = store.get_jd(c.job_id)
        if jd:
            expl, qs = await ai.analyze_candidate(jd.parsed, c.parsed, c.scores)
            c.explanation = expl
            c.interview_questions = qs
    return _detail(c)


# --------------------------------------------------------------------------
# Copilot chat
# --------------------------------------------------------------------------
@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    candidates = store.candidates_for_job(body.job_id)
    if not candidates:
        raise HTTPException(404, "No screened candidates for this job yet.")
    jd = store.get_jd(store.get_job(body.job_id).jd_id) if store.get_job(body.job_id) else None
    lines = []
    if jd:
        lines.append(f"ROLE: {jd.parsed.role} ({jd.parsed.seniority}); must-have: {', '.join(jd.parsed.must_have)}")
    for c in candidates[:25]:
        lines.append(
            f"#{c.rank} {c.parsed.name} — {c.scores.overall:.0f}% | "
            f"{c.parsed.years_of_experience:.0f}y | skills: {', '.join(c.parsed.skills[:6])} | "
            f"missing: {', '.join(c.missing_skills) or 'none'}"
            + (" | HIDDEN GEM" if c.is_hidden_gem else "")
        )
    response = await ai.chat(body.message, "\n".join(lines))
    return ChatResponse(response=response)


# --------------------------------------------------------------------------
# Compare
# --------------------------------------------------------------------------
@router.post("/compare", response_model=list[CandidateDetail])
async def compare(body: CompareRequest):
    out = []
    for cid in body.candidate_ids:
        c = store.get_candidate(cid)
        if c:
            out.append(_detail(c))
    if not out:
        raise HTTPException(404, "None of the candidates were found.")
    return out


# --------------------------------------------------------------------------
# Exports
# --------------------------------------------------------------------------
@router.get("/export/csv/{job_id}")
async def export_csv(job_id: str):
    job = store.get_job(job_id)
    if not job or job.status != "done":
        raise HTTPException(404, "No completed screening for this job.")
    candidates = store.candidates_for_job(job_id)
    data = report.candidates_csv(candidates)
    return StreamingResponse(
        iter([data]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=shortlist_{job_id}.csv"},
    )


@router.get("/export/pdf/{candidate_id}")
async def export_pdf(candidate_id: str):
    c = store.get_candidate(candidate_id)
    if not c:
        raise HTTPException(404, "Candidate not found.")
    jd = store.get_jd(c.job_id)
    pdf_bytes = report.candidate_pdf(c, jd)
    return StreamingResponse(
        iter([pdf_bytes]), media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={c.parsed.name.replace(' ', '_')}.pdf"},
    )


# --------------------------------------------------------------------------
# Converters
# --------------------------------------------------------------------------
def _summary(c) -> CandidateSummary:
    return CandidateSummary(
        id=c.id, rank=c.rank, name=c.parsed.name, headline=c.parsed.headline,
        overall=c.scores.overall if c.scores else 0.0,
        years_of_experience=c.parsed.years_of_experience,
        top_skills=c.matched_skills[:6] or c.parsed.skills[:6],
        recommendation=c.explanation.recommendation if c.explanation else "",
        is_hidden_gem=c.is_hidden_gem,
        summary=c.explanation.summary if c.explanation else "",
    )


def _detail(c) -> CandidateDetail:
    from app.schemas import ScoreBreakdown, Explanation
    return CandidateDetail(
        id=c.id, rank=c.rank, parsed=c.parsed,
        scores=c.scores or ScoreBreakdown(),
        explanation=c.explanation or Explanation(),
        matched_skills=c.matched_skills,
        missing_skills=c.missing_skills,
        interview_questions=c.interview_questions,
        is_hidden_gem=c.is_hidden_gem,
    )
