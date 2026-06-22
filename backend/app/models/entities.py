from __future__ import annotations
import uuid
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Text, Float, Integer, Boolean, DateTime, ForeignKey, JSON, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), default="Untitled Role")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    parsed_data: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    candidates: Mapped[list["Candidate"]] = relationship(back_populates="job_description")
    diversity_reports: Mapped[list["DiversityReport"]] = relationship(back_populates="job_description")


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_description_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("job_descriptions.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), default="Unknown")
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    parsed_data: Mapped[dict] = mapped_column(JSON, default=dict)
    years_of_experience: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(50), default="processed")
    is_hidden_gem: Mapped[bool] = mapped_column(Boolean, default=False)
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job_description: Mapped[Optional[JobDescription]] = relationship(back_populates="candidates")
    skills: Mapped[list["CandidateSkill"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    experiences: Mapped[list["CandidateExperience"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    scores: Mapped[Optional[CandidateScore]] = relationship(
        back_populates="candidate", uselist=False, cascade="all, delete-orphan"
    )
    interview_questions: Mapped[list["InterviewQuestion"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )


class CandidateSkill(Base):
    __tablename__ = "candidate_skills"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id"))
    skill_name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(50), default="technical")

    candidate: Mapped["Candidate"] = relationship(back_populates="skills")


class CandidateExperience(Base):
    __tablename__ = "candidate_experience"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id"))
    company: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(255), default="")
    start_date: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    end_date: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    candidate: Mapped["Candidate"] = relationship(back_populates="experiences")


class CandidateScore(Base):
    __tablename__ = "candidate_scores"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id"), unique=True)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    skill_score: Mapped[float] = mapped_column(Float, default=0.0)
    experience_score: Mapped[float] = mapped_column(Float, default=0.0)
    domain_score: Mapped[float] = mapped_column(Float, default=0.0)
    education_score: Mapped[float] = mapped_column(Float, default=0.0)
    soft_skill_score: Mapped[float] = mapped_column(Float, default=0.0)
    explanation: Mapped[dict] = mapped_column(JSON, default=dict)
    executive_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    candidate: Mapped["Candidate"] = relationship(back_populates="scores")


class InterviewQuestion(Base):
    __tablename__ = "interview_questions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id"))
    category: Mapped[str] = mapped_column(String(50))
    question: Mapped[str] = mapped_column(Text)

    candidate: Mapped["Candidate"] = relationship(back_populates="interview_questions")


class DiversityReport(Base):
    __tablename__ = "diversity_reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_description_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("job_descriptions.id"))
    alerts: Mapped[list] = mapped_column(JSON, default=list)
    insights: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job_description: Mapped["JobDescription"] = relationship(back_populates="diversity_reports")


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_description_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("job_descriptions.id"), nullable=True
    )
    session_id: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_description_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("job_descriptions.id"), nullable=True
    )
    job_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default=ProcessingStatus.PENDING.value)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
