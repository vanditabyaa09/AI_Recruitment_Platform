"""High-level AI tasks built on the Gemini client, each with a deterministic
heuristic fallback so the product degrades gracefully (never crashes, never
returns empty) when the API is unavailable or rate-limited."""
from __future__ import annotations

import re
import logging

from app.config import get_settings
from app.gemini import gemini
from app.schemas import (
    ParsedJD, ParsedCV, EducationItem, ExperienceItem,
    ScoreBreakdown, Explanation, InterviewQuestion,
)

logger = logging.getLogger("recruitiq.ai")
settings = get_settings()

MAX_DOC_CHARS = 9000


# ==========================================================================
# Job description parsing
# ==========================================================================
_JD_SYSTEM = """You are an expert technical recruiter. Extract structured data from a job description.
Return ONLY JSON with these keys:
- role (string): the job title
- seniority (string): Junior | Mid | Senior | Lead | Principal
- experience_required (string): human-readable, e.g. "5+ years"
- min_years (number): minimum years of experience as a number
- hard_skills (string[]): concrete technical skills/tools
- soft_skills (string[])
- must_have (string[]): non-negotiable requirements
- nice_to_have (string[])
- domain_knowledge (string[]): industries/domains
- education_requirements (string[])
- responsibilities (string[]): key responsibilities
- confidence (object): map each field name to a 0-1 confidence number
Be faithful to the text. Do not invent skills that aren't implied."""


async def parse_jd(text: str) -> tuple[ParsedJD, dict]:
    text = text[:MAX_DOC_CHARS]
    if gemini.available:
        try:
            data = await gemini.generate_json(_JD_SYSTEM, text)
            confidence = data.pop("confidence", {}) if isinstance(data, dict) else {}
            jd = _coerce_jd(data)
            return jd, {k: float(v) for k, v in confidence.items() if _isnum(v)}
        except Exception as e:
            logger.warning("JD parse via AI failed, using heuristic: %s", e)
    return _heuristic_jd(text), {}


def _coerce_jd(data: dict) -> ParsedJD:
    if not isinstance(data, dict):
        return ParsedJD()
    return ParsedJD(
        role=str(data.get("role", "") or ""),
        seniority=str(data.get("seniority", "") or ""),
        experience_required=str(data.get("experience_required", "") or ""),
        min_years=_to_float(data.get("min_years")),
        hard_skills=_as_list(data.get("hard_skills")),
        soft_skills=_as_list(data.get("soft_skills")),
        must_have=_as_list(data.get("must_have")),
        nice_to_have=_as_list(data.get("nice_to_have")),
        domain_knowledge=_as_list(data.get("domain_knowledge")),
        education_requirements=_as_list(data.get("education_requirements")),
        responsibilities=_as_list(data.get("responsibilities")),
    )


# ==========================================================================
# CV parsing — BATCHED (many CVs per LLM call to fit rate limits + <60s)
# ==========================================================================
_CV_BATCH_SYSTEM = """You are an expert resume parser. You will receive several CVs, each delimited by
a line "=== CV {index} ===". Parse EACH into structured data.
Return ONLY a JSON array, one object per CV in order, each with keys:
- index (number): the CV index given
- name, email, phone, location (strings; null if absent)
- headline (string): one-line professional summary
- years_of_experience (number)
- skills (string[])
- education (array of {institution, degree, field, year})
- certifications (string[])
- experience (array of {company, role, start, end, highlights[]})
- projects (array of {name, description})
- achievements (string[])
Extract only what's present. Do not fabricate."""


async def parse_cv_batch(docs: list[tuple[int, str]]) -> dict[int, ParsedCV]:
    """docs: list of (index, raw_text). Returns {index: ParsedCV}."""
    if gemini.available and docs:
        try:
            blocks = [f"=== CV {idx} ===\n{txt[:MAX_DOC_CHARS]}" for idx, txt in docs]
            user = "\n\n".join(blocks)
            # ~ generous token budget: roughly per-CV structured output
            data = await gemini.generate_json(
                _CV_BATCH_SYSTEM, user, max_tokens=900 * len(docs) + 512,
            )
            items = data if isinstance(data, list) else data.get("cvs", []) if isinstance(data, dict) else []
            result: dict[int, ParsedCV] = {}
            for obj in items:
                if not isinstance(obj, dict):
                    continue
                idx = int(obj.get("index", -1))
                result[idx] = _coerce_cv(obj)
            # Fill any the model dropped with heuristic parse.
            for idx, txt in docs:
                if idx not in result:
                    logger.warning("CV index %d missing from AI batch, heuristic fallback", idx)
                    result[idx] = _heuristic_cv(txt)
            return result
        except Exception as e:
            logger.warning("CV batch parse via AI failed, using heuristic: %s", e)
    return {idx: _heuristic_cv(txt) for idx, txt in docs}


def _coerce_cv(data: dict) -> ParsedCV:
    edu = [EducationItem(
        institution=str(e.get("institution", "") or ""),
        degree=str(e.get("degree", "") or ""),
        field=str(e.get("field", "") or ""),
        year=str(e.get("year", "") or ""),
    ) for e in data.get("education", []) if isinstance(e, dict)]
    exp = [ExperienceItem(
        company=str(x.get("company", "") or ""),
        role=str(x.get("role", "") or ""),
        start=str(x.get("start", "") or ""),
        end=str(x.get("end", "") or ""),
        highlights=_as_list(x.get("highlights")),
    ) for x in data.get("experience", []) if isinstance(x, dict)]
    return ParsedCV(
        name=str(data.get("name") or "Unknown Candidate"),
        email=_clean(data.get("email")),
        phone=_clean(data.get("phone")),
        location=_clean(data.get("location")),
        headline=str(data.get("headline", "") or ""),
        years_of_experience=_to_float(data.get("years_of_experience")),
        skills=_as_list(data.get("skills")),
        education=edu,
        certifications=_as_list(data.get("certifications")),
        experience=exp,
        projects=[p for p in data.get("projects", []) if isinstance(p, dict)],
        achievements=_as_list(data.get("achievements")),
    )


# ==========================================================================
# Explanation + tailored interview questions (one combined call)
# ==========================================================================
_ANALYZE_SYSTEM = """You are a senior recruiter writing a candidate evaluation for a hiring manager.
Given a job description, a candidate's parsed CV, and computed fit scores, return ONLY JSON:
{
 "explanation": {
   "summary": "2-3 sentence verdict naming the candidate and their fit, specific to THIS person",
   "strengths": ["concrete strengths tied to the CV"],
   "gaps": ["specific missing requirements or risks"],
   "flags": ["anything to verify, e.g. short tenures, career gaps"],
   "recommendation": "strong_yes | yes | maybe | no"
 },
 "questions": [
   {"category": "technical|behavioral|gap_probing|project_deep_dive",
    "question": "a question that references SPECIFIC CV content (a named project, company, skill, or gap)"}
 ]
}
Generate 4-6 questions. Questions MUST be specific to this candidate — no generic boilerplate."""


_ANALYZE_BATCH_SYSTEM = """You are a senior recruiter evaluating several candidates for one role.
You receive the job description and a JSON array of candidates (each has an "index", their parsed
CV, and computed fit scores). For EACH candidate return an evaluation.
Return ONLY a JSON array, one object per candidate in the same order, each:
{
 "index": <the candidate index>,
 "explanation": {
   "summary": "2-3 sentence verdict naming the candidate, specific to THEM",
   "strengths": ["concrete strengths tied to their CV"],
   "gaps": ["specific missing requirements or risks"],
   "flags": ["things to verify, e.g. short tenures, gaps"],
   "recommendation": "strong_yes | yes | maybe | no"
 },
 "questions": [
   {"category": "technical|behavioral|gap_probing|project_deep_dive",
    "question": "references SPECIFIC content from THIS candidate's CV"}
 ]
}
Give 4-5 questions each. Every question MUST be specific to that candidate — never generic, never
copied between candidates."""


async def analyze_candidates_batch(
    jd: ParsedJD, items: list[tuple[str, ParsedCV, ScoreBreakdown]]
) -> dict[str, tuple[Explanation, list[InterviewQuestion]]]:
    """items: list of (candidate_id, cv, scores). Evaluates all in one LLM call.
    Returns {candidate_id: (explanation, questions)}. Falls back per-candidate."""
    if not items:
        return {}
    if gemini.available:
        try:
            id_by_index = {i: cid for i, (cid, _, _) in enumerate(items)}
            payload = [
                {"index": i, "cv": cv.model_dump(), "scores": sc.model_dump()}
                for i, (_, cv, sc) in enumerate(items)
            ]
            import json as _json
            user = f"JOB DESCRIPTION:\n{jd.model_dump_json()}\n\nCANDIDATES:\n{_json.dumps(payload)}"
            data = await gemini.generate_json(
                _ANALYZE_BATCH_SYSTEM, user,
                max_tokens=700 * len(items) + 512, temperature=0.4,
            )
            arr = data if isinstance(data, list) else data.get("candidates", []) if isinstance(data, dict) else []
            out: dict[str, tuple[Explanation, list[InterviewQuestion]]] = {}
            for obj in arr:
                if not isinstance(obj, dict):
                    continue
                cid = id_by_index.get(int(obj.get("index", -1)))
                if cid is None:
                    continue
                expl = _coerce_explanation(obj.get("explanation", {}))
                qs = [InterviewQuestion(category=str(q.get("category", "technical")),
                                        question=str(q.get("question", "")).strip())
                      for q in obj.get("questions", []) if isinstance(q, dict) and q.get("question")]
                out[cid] = (expl, qs)
            # Fill any the model dropped with heuristic.
            for cid, cv, sc in items:
                if cid not in out:
                    out[cid] = (_heuristic_explanation(jd, cv, sc), _heuristic_questions(jd, cv))
            return out
        except Exception as e:
            logger.warning("Batch analysis via AI failed, using heuristic: %s", e)
    return {cid: (_heuristic_explanation(jd, cv, sc), _heuristic_questions(jd, cv))
            for cid, cv, sc in items}


async def analyze_candidate(jd: ParsedJD, cv: ParsedCV, scores: ScoreBreakdown
                            ) -> tuple[Explanation, list[InterviewQuestion]]:
    if gemini.available:
        try:
            user = (
                f"JOB DESCRIPTION:\n{jd.model_dump_json()}\n\n"
                f"CANDIDATE CV:\n{cv.model_dump_json()}\n\n"
                f"FIT SCORES (0-100):\n{scores.model_dump_json()}"
            )
            data = await gemini.generate_json(_ANALYZE_SYSTEM, user, max_tokens=1800, temperature=0.4)
            if isinstance(data, dict) and "explanation" in data:
                expl = _coerce_explanation(data["explanation"])
                qs = [InterviewQuestion(
                        category=str(q.get("category", "technical")),
                        question=str(q.get("question", "")).strip(),
                      ) for q in data.get("questions", []) if isinstance(q, dict) and q.get("question")]
                if not qs:
                    qs = _heuristic_questions(jd, cv)
                return expl, qs
        except Exception as e:
            logger.warning("Candidate analysis via AI failed, using heuristic: %s", e)
    return _heuristic_explanation(jd, cv, scores), _heuristic_questions(jd, cv)


def _coerce_explanation(d: dict) -> Explanation:
    if not isinstance(d, dict):
        return Explanation()
    return Explanation(
        summary=str(d.get("summary", "") or ""),
        strengths=_as_list(d.get("strengths")),
        gaps=_as_list(d.get("gaps")),
        flags=_as_list(d.get("flags")),
        recommendation=str(d.get("recommendation", "maybe") or "maybe"),
    )


# ==========================================================================
# Copilot chat
# ==========================================================================
async def chat(message: str, context: str) -> str:
    system = ("You are RecruitIQ Copilot, a recruiting assistant. Answer using ONLY the "
              "candidate pool data provided. Be concise, specific, and actionable. "
              "Reference candidates by name when relevant.")
    if gemini.available:
        try:
            return await gemini.generate_text(system, f"POOL DATA:\n{context}\n\nQUESTION: {message}",
                                               max_tokens=700, temperature=0.4)
        except Exception as e:
            logger.warning("Chat via AI failed: %s", e)
    return ("I'm running in offline mode right now, but based on the ranked pool you can filter "
            "by skill, open any candidate for a full gap analysis, and check the Diversity panel "
            "for hidden gems that scored well with non-traditional backgrounds.")


# ==========================================================================
# Heuristic fallbacks (deterministic, token-free)
# ==========================================================================
_SKILL_VOCAB = [
    "python", "javascript", "typescript", "java", "go", "rust", "c++", "c#", "ruby", "php",
    "react", "vue", "angular", "node", "fastapi", "django", "flask", "spring",
    "postgresql", "mysql", "mongodb", "redis", "kafka", "rabbitmq", "elasticsearch",
    "aws", "gcp", "azure", "docker", "kubernetes", "terraform", "ci/cd", "jenkins",
    "sql", "graphql", "rest", "microservices", "system design",
    "machine learning", "deep learning", "nlp", "pytorch", "tensorflow", "pandas",
    "numpy", "scikit-learn", "spark", "airflow", "tableau", "power bi", "excel",
]
_SOFT_VOCAB = ["communication", "leadership", "teamwork", "mentoring", "problem solving",
               "collaboration", "stakeholder", "ownership"]


def _heuristic_jd(text: str) -> ParsedJD:
    low = text.lower()
    hard = [s for s in _SKILL_VOCAB if s in low]
    soft = [s for s in _SOFT_VOCAB if s in low]
    seniority = ("Principal" if "principal" in low else "Lead" if "lead" in low
                 else "Senior" if "senior" in low else "Junior" if "junior" in low else "Mid")
    m = re.search(r"(\d+)\+?\s*years?", low)
    min_years = float(m.group(1)) if m else 3.0
    first_line = next((l.strip() for l in text.splitlines() if l.strip()), "Role")
    return ParsedJD(
        role=first_line[:80],
        seniority=seniority,
        experience_required=f"{int(min_years)}+ years",
        min_years=min_years,
        hard_skills=[s.title() if s.islower() else s for s in hard][:12] or ["Python", "SQL"],
        soft_skills=[s.title() for s in soft] or ["Communication", "Teamwork"],
        must_have=[s.title() if s.islower() else s for s in hard][:4] or ["Python"],
        nice_to_have=[s.title() if s.islower() else s for s in hard][4:8],
        domain_knowledge=[],
        education_requirements=["Bachelor's degree or equivalent experience"],
        responsibilities=[],
    )


def _heuristic_cv(text: str) -> ParsedCV:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    low = text.lower()
    name = lines[0][:80] if lines else "Unknown Candidate"
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phone = re.search(r"\+?\d[\d\s().-]{8,}\d", text)
    m = re.search(r"(\d+)\+?\s*years?", low)
    years = float(m.group(1)) if m else 3.0
    skills = [s.title() if s.islower() else s for s in _SKILL_VOCAB if s in low][:18]
    companies = [l[:80] for l in lines[:40]
                 if any(k in l.lower() for k in ["inc", "corp", "ltd", "llc", "technologies", "systems", "labs"])]
    exp = [ExperienceItem(company=c, role="", start="", end="", highlights=[]) for c in companies[:4]]
    return ParsedCV(
        name=name,
        email=email.group() if email else None,
        phone=phone.group().strip() if phone else None,
        headline=lines[1][:120] if len(lines) > 1 else "",
        years_of_experience=years,
        skills=skills or ["Python"],
        experience=exp,
    )


def _heuristic_explanation(jd: ParsedJD, cv: ParsedCV, scores: ScoreBreakdown) -> Explanation:
    cv_skills = {s.lower() for s in cv.skills}
    missing = [m for m in jd.must_have if m.lower() not in cv_skills]
    matched = [s for s in (jd.must_have + jd.hard_skills) if s.lower() in cv_skills]
    matched = list(dict.fromkeys(matched))
    rec = ("strong_yes" if scores.overall >= 80 else "yes" if scores.overall >= 65
           else "maybe" if scores.overall >= 50 else "no")

    req = jd.min_years or 0
    exp_phrase = (f"{cv.years_of_experience:.0f} years of experience"
                  + (f", meeting the {req:.0f}+ year requirement" if req and cv.years_of_experience >= req
                     else f", short of the {req:.0f}+ year requirement" if req else ""))
    role = jd.role or "the role"
    fit = "strong" if scores.overall >= 75 else "solid" if scores.overall >= 60 else "partial"
    summary = (f"{cv.name} is a {fit} fit for {role} ({scores.overall:.0f}% overall), with {exp_phrase}. "
               + (f"Covers {len(matched)} of the key skills including {', '.join(matched[:4])}."
                  if matched else "Skill overlap with the role is limited.")
               + (f" Missing {', '.join(missing[:3])}." if missing else ""))

    strengths: list[str] = []
    if cv.years_of_experience and req and cv.years_of_experience >= req:
        strengths.append(f"{cv.years_of_experience:.0f}y experience exceeds the {req:.0f}+ year bar")
    for s in matched[:4]:
        strengths.append(f"Hands-on with {s}")
    top_co = next((x.company for x in cv.experience if x.company), None)
    if top_co:
        strengths.append(f"Prior role at {top_co}")
    if not strengths:
        strengths = [f"{cv.years_of_experience:.0f} years of experience"]

    gaps = [f"No clear evidence of {m}" for m in missing[:4]]
    flags = []
    if req and cv.years_of_experience and cv.years_of_experience < req:
        flags.append(f"Below the {req:.0f}+ year experience target")
    if not cv.education:
        flags.append("No formal education listed — verify background")

    return Explanation(
        summary=summary,
        strengths=strengths[:5],
        gaps=gaps,
        flags=flags,
        recommendation=rec,
    )


def _heuristic_questions(jd: ParsedJD, cv: ParsedCV) -> list[InterviewQuestion]:
    qs: list[InterviewQuestion] = []
    for p in cv.projects[:1]:
        name = p.get("name") if isinstance(p, dict) else None
        if name:
            qs.append(InterviewQuestion(category="project_deep_dive",
                question=f"Walk me through {name} — what was the hardest technical decision and why?"))
    for x in cv.experience[:1]:
        if x.company:
            qs.append(InterviewQuestion(category="behavioral",
                question=f"At {x.company}, tell me about a time you had to deliver under pressure across teams."))
    for s in cv.skills[:2]:
        qs.append(InterviewQuestion(category="technical",
            question=f"Describe a challenging problem you solved using {s} and the tradeoffs you weighed."))
    cv_skills = {s.lower() for s in cv.skills}
    for m in jd.must_have:
        if m.lower() not in cv_skills:
            qs.append(InterviewQuestion(category="gap_probing",
                question=f"This role needs {m}, which isn't obvious on your CV. How have you worked with it?"))
            break
    return qs[:6]


# ==========================================================================
# small utils
# ==========================================================================
def _as_list(v) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return []


def _to_float(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"\d+(\.\d+)?", v)
        if m:
            return float(m.group())
    return 0.0


def _isnum(v) -> bool:
    return isinstance(v, (int, float)) or (isinstance(v, str) and v.replace(".", "", 1).isdigit())


def _clean(v):
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s.lower() not in ("null", "none", "n/a") else None
