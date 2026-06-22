"""In-memory data store. No database — everything lives in RAM for the
lifetime of the process and resets on restart. Simple dict-backed registries
keyed by uuid string."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

from app.schemas import (
    ParsedJD, ParsedCV, ScoreBreakdown, Explanation, InterviewQuestion,
)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class JobDescription:
    id: str
    title: str
    raw_text: str
    parsed: ParsedJD
    confidence: dict
    embedding: Optional[list[float]] = None


@dataclass
class Candidate:
    id: str
    job_id: str
    filename: str
    raw_text: str
    parsed: ParsedCV
    embedding: Optional[list[float]] = None
    scores: Optional[ScoreBreakdown] = None
    explanation: Optional[Explanation] = None
    interview_questions: list[InterviewQuestion] = field(default_factory=list)
    rank: int = 0
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    is_hidden_gem: bool = False


@dataclass
class ScreeningJob:
    id: str
    jd_id: str
    status: str = "pending"
    progress: int = 0
    total: int = 0
    processed: int = 0
    message: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    using_ai: bool = True
    candidate_ids: list[str] = field(default_factory=list)
    diversity: Optional[dict] = None
    error: str = ""


class Store:
    def __init__(self) -> None:
        self.jds: dict[str, JobDescription] = {}
        self.candidates: dict[str, Candidate] = {}
        self.jobs: dict[str, ScreeningJob] = {}

    # --- job descriptions ---
    def add_jd(self, jd: JobDescription) -> None:
        self.jds[jd.id] = jd

    def get_jd(self, jd_id: str) -> Optional[JobDescription]:
        return self.jds.get(jd_id)

    # --- candidates ---
    def add_candidate(self, c: Candidate) -> None:
        self.candidates[c.id] = c

    def get_candidate(self, cid: str) -> Optional[Candidate]:
        return self.candidates.get(cid)

    def candidates_for_job(self, job_id: str) -> list[Candidate]:
        job = self.jobs.get(job_id)
        if not job:
            return []
        cs = [self.candidates[cid] for cid in job.candidate_ids if cid in self.candidates]
        return sorted(cs, key=lambda c: c.rank or 9999)

    # --- screening jobs ---
    def add_job(self, job: ScreeningJob) -> None:
        self.jobs[job.id] = job

    def get_job(self, job_id: str) -> Optional[ScreeningJob]:
        return self.jobs.get(job_id)


store = Store()
