"""Pydantic models: parsed AI structures, API requests and responses."""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional


# --------------------------------------------------------------------------
# Parsed AI structures
# --------------------------------------------------------------------------
class ParsedJD(BaseModel):
    role: str = ""
    seniority: str = ""
    experience_required: str = ""
    min_years: float = 0.0
    hard_skills: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    must_have: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    domain_knowledge: list[str] = Field(default_factory=list)
    education_requirements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)


class EducationItem(BaseModel):
    institution: str = ""
    degree: str = ""
    field: str = ""
    year: str = ""


class ExperienceItem(BaseModel):
    company: str = ""
    role: str = ""
    start: str = ""
    end: str = ""
    highlights: list[str] = Field(default_factory=list)


class ParsedCV(BaseModel):
    name: str = "Unknown Candidate"
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    headline: str = ""
    years_of_experience: float = 0.0
    skills: list[str] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list)
    projects: list[dict] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    overall: float = 0.0
    skills: float = 0.0
    experience: float = 0.0
    domain: float = 0.0
    education: float = 0.0
    soft_skills: float = 0.0
    semantic: float = 0.0


class Explanation(BaseModel):
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    recommendation: str = ""  # strong_yes | yes | maybe | no


class InterviewQuestion(BaseModel):
    category: str = "technical"  # technical | behavioral | gap_probing | project_deep_dive
    question: str


# --------------------------------------------------------------------------
# API requests
# --------------------------------------------------------------------------
class JDTextRequest(BaseModel):
    text: str


class ChatRequest(BaseModel):
    message: str
    job_id: str


class CompareRequest(BaseModel):
    job_id: str
    candidate_ids: list[str]


# --------------------------------------------------------------------------
# API responses
# --------------------------------------------------------------------------
class JDResponse(BaseModel):
    id: str
    title: str
    parsed: ParsedJD
    confidence: dict[str, float] = Field(default_factory=dict)


class JobStatus(BaseModel):
    id: str
    jd_id: str
    status: str            # pending | parsing | ranking | explaining | done | failed
    progress: int          # 0-100
    total: int
    processed: int
    message: str = ""
    elapsed_seconds: float = 0.0
    using_ai: bool = True


class CandidateSummary(BaseModel):
    id: str
    rank: int
    name: str
    headline: str = ""
    overall: float
    years_of_experience: float
    top_skills: list[str] = Field(default_factory=list)
    recommendation: str = ""
    is_hidden_gem: bool = False
    summary: str = ""


class CandidateDetail(BaseModel):
    id: str
    rank: int
    parsed: ParsedCV
    scores: ScoreBreakdown
    explanation: Explanation
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    interview_questions: list[InterviewQuestion] = Field(default_factory=list)
    is_hidden_gem: bool = False


class DiversityFlag(BaseModel):
    severity: str          # info | warning
    title: str
    detail: str


class DiversityReport(BaseModel):
    skewed: bool = False
    flags: list[DiversityFlag] = Field(default_factory=list)
    hidden_gems: list[CandidateSummary] = Field(default_factory=list)
    shortlist_size: int = 0
    distribution: dict = Field(default_factory=dict)


class ResultsResponse(BaseModel):
    job_id: str
    jd: JDResponse
    candidates: list[CandidateSummary]
    diversity: DiversityReport
    using_ai: bool = True
    elapsed_seconds: float = 0.0


class ChatResponse(BaseModel):
    response: str
