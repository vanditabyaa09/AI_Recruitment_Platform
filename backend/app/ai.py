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
# Explanation (auto, batched) — questions are generated separately on demand
# ==========================================================================
_EXPLAIN_BATCH_SYSTEM = """You are a senior recruiter evaluating several candidates for one role.
You receive the job description and a JSON array of candidates (each has an "index", their parsed
CV, and computed fit scores). For EACH candidate return an evaluation.
Return ONLY a JSON array, one object per candidate in the same order, each:
{
 "index": <the candidate index>,
 "summary": "2-3 sentence verdict naming the candidate, specific to THEM",
 "strengths": ["concrete strengths tied to their CV"],
 "gaps": ["specific missing requirements or risks"],
 "flags": ["things to verify, e.g. short tenures, gaps"],
 "recommendation": "strong_yes | yes | maybe | no"
}
Be specific to each candidate — never generic, never copied between candidates."""


async def explain_candidates_batch(
    jd: ParsedJD, items: list[tuple[str, ParsedCV, ScoreBreakdown]]
) -> dict[str, Explanation]:
    """items: list of (candidate_id, cv, scores). Writes a fit explanation for
    each in one LLM call. Returns {candidate_id: Explanation}. Interview
    questions are NOT generated here — they are produced on demand per candidate
    (see generate_questions)."""
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
                _EXPLAIN_BATCH_SYSTEM, user,
                max_tokens=420 * len(items) + 512, temperature=0.4,
            )
            arr = data if isinstance(data, list) else data.get("candidates", []) if isinstance(data, dict) else []
            out: dict[str, Explanation] = {}
            for obj in arr:
                if not isinstance(obj, dict):
                    continue
                cid = id_by_index.get(int(obj.get("index", -1)))
                if cid is None:
                    continue
                out[cid] = _coerce_explanation(obj)
            for cid, cv, sc in items:
                if cid not in out:
                    out[cid] = _heuristic_explanation(jd, cv, sc)
            return out
        except Exception as e:
            logger.warning("Batch explanation via AI failed, using heuristic: %s", e)
    return {cid: _heuristic_explanation(jd, cv, sc) for cid, cv, sc in items}


# ==========================================================================
# Tailored interview questions — generated ON DEMAND for a single candidate
# ==========================================================================
_QUESTIONS_SYSTEM = """You are a senior interviewer building an interview kit for ONE candidate.
You are given the JOB DESCRIPTION, the candidate's parsed CV, and their fit scores. Your job is to
CROSS-REFERENCE the two: for each requirement in the JD, look at what the candidate's CV actually
shows, and write a question that pressure-tests the overlap (or the gap).

Return ONLY JSON: {"questions": [
  {"category": "technical|behavioral|gap_probing|project_deep_dive|system_design|role_fit",
   "question": "the question",
   "rationale": "one short clause on what it probes and why it matters for THIS role"}
]}

Generate 8-10 questions with this coverage:
  - 2-3 PROJECT_DEEP_DIVE: name a specific project/achievement from the CV and dig into their
    decisions, scale, and tradeoffs.
  - 2 TECHNICAL: about a must-have skill the candidate claims — go beyond "have you used X" to a
    concrete scenario relevant to the role's responsibilities.
  - 1-2 GAP_PROBING: target a must-have or domain in the JD that is weak/absent on the CV.
  - 1 SYSTEM_DESIGN or ROLE_FIT: tied to the seniority and responsibilities in the JD.
  - 1-2 BEHAVIORAL: anchored to a real company/role/tenure on the CV.

Every question MUST reference SPECIFIC CV content (a named project, employer, skill, number, or
gap) AND connect to a JD requirement. No generic boilerplate, no question reusable for another
candidate."""


async def generate_questions(jd: ParsedJD, cv: ParsedCV, scores: ScoreBreakdown
                             ) -> list[InterviewQuestion]:
    if gemini.available:
        try:
            user = (
                f"JOB DESCRIPTION:\n{jd.model_dump_json()}\n\n"
                f"CANDIDATE CV:\n{cv.model_dump_json()}\n\n"
                f"FIT SCORES (0-100):\n{scores.model_dump_json()}"
            )
            data = await gemini.generate_json(_QUESTIONS_SYSTEM, user, max_tokens=2200, temperature=0.6)
            items = data.get("questions") if isinstance(data, dict) else data if isinstance(data, list) else []
            qs = []
            for q in (items or []):
                if not isinstance(q, dict) or not q.get("question"):
                    continue
                text = str(q["question"]).strip()
                rationale = str(q.get("rationale", "")).strip()
                if rationale:
                    text = f"{text}  ↳ {rationale}"
                qs.append(InterviewQuestion(category=str(q.get("category", "technical")), question=text))
            if qs:
                return qs
        except Exception as e:
            logger.warning("Question generation via AI failed, using heuristic: %s", e)
    return _heuristic_questions(jd, cv)


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
    # Word-boundary checks; "senior" wins over a stray "lead" inside "leadership".
    seniority = ("Principal" if re.search(r"\bprincipal\b", low)
                 else "Senior" if re.search(r"\bsenior\b|\bsr\.?\b", low)
                 else "Lead" if re.search(r"\b(lead|staff)\b", low)
                 else "Junior" if re.search(r"\bjunior\b|\bjr\.?\b", low)
                 else "Mid")
    m = re.search(r"(\d+)\+?\s*years?", low)
    min_years = float(m.group(1)) if m else 3.0
    first_line = next((l.strip() for l in text.splitlines() if l.strip()), "Role")
    # Clip at the first sentence/clause so a one-line JD doesn't make the whole
    # paragraph the "role".
    role = re.split(r"[.\n;|–—]", first_line)[0].strip()[:60] or "Role"
    return ParsedJD(
        role=role,
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
    """Combine JD requirements with the candidate's actual CV to build a varied,
    role-grounded question set (used when the LLM is unavailable)."""
    qs: list[InterviewQuestion] = []
    role = jd.role or "this role"
    cv_skills = {s.lower() for s in cv.skills}
    matched = list(dict.fromkeys(s for s in (jd.must_have + jd.hard_skills) if s.lower() in cv_skills))
    missing = [m for m in jd.must_have if m.lower() not in cv_skills]

    # Project deep-dives — name the candidate's actual projects.
    for p in cv.projects[:2]:
        if not isinstance(p, dict):
            continue
        name, desc = p.get("name"), p.get("description")
        if name:
            extra = f" (you describe it as \"{desc}\")" if desc else ""
            qs.append(InterviewQuestion(category="project_deep_dive",
                question=(f"Walk me through {name}{extra}. What was the hardest technical decision, how did "
                          f"you measure success, and how does it map to what we need in {role}?")))

    # Technical — must-have skills the candidate actually claims.
    for s in matched[:3]:
        qs.append(InterviewQuestion(category="technical",
            question=(f"This role relies heavily on {s}. Describe a production problem you solved with {s}, "
                      f"the alternatives you considered, and the tradeoffs you accepted.")))

    # Gap-probing — must-haves missing from the CV.
    for m in missing[:2]:
        qs.append(InterviewQuestion(category="gap_probing",
            question=(f"The role lists {m} as a must-have, but it isn't evident on your CV. Where have you "
                      f"touched {m}, and how would you get to production-level proficiency quickly?")))

    # Seniority / experience fit.
    if jd.min_years and cv.years_of_experience:
        if cv.years_of_experience < jd.min_years:
            qs.append(InterviewQuestion(category="role_fit",
                question=(f"This is a {jd.seniority or 'senior'} role targeting {jd.min_years:.0f}+ years and "
                          f"you have about {cv.years_of_experience:.0f}. What scope of ownership have you held "
                          f"that shows you can operate at this level?")))
        else:
            qs.append(InterviewQuestion(category="behavioral",
                question=(f"With ~{cv.years_of_experience:.0f} years of experience, tell me about a time you set "
                          f"technical direction or mentored others toward a hard deadline.")))

    # Behavioral — anchored to a real employer.
    for x in cv.experience[:1]:
        if x.company:
            role_at = f" as {x.role}" if x.role else ""
            qs.append(InterviewQuestion(category="behavioral",
                question=(f"At {x.company}{role_at}, describe a time you had to align stakeholders or deliver "
                          f"under pressure. What would you do differently now?")))

    # Domain knowledge from the JD.
    for d in jd.domain_knowledge[:1]:
        qs.append(InterviewQuestion(category="technical",
            question=(f"We work in {d}. What domain-specific challenges have you faced there, and how did they "
                      f"shape your technical choices?")))

    # Nice-to-have depth.
    for nt in jd.nice_to_have[:1]:
        qs.append(InterviewQuestion(category="technical",
            question=(f"Beyond the core requirements we also value {nt}. What's your hands-on exposure to it, "
                      f"and where have you applied it?")))

    # Achievement-based.
    for a in cv.achievements[:1]:
        qs.append(InterviewQuestion(category="behavioral",
            question=(f"You list \"{a}\" as an achievement. What was your specific contribution, and how would "
                      f"you reproduce that kind of impact in this role?")))

    # System design for senior+ roles.
    if (jd.seniority or "").lower() in ("senior", "lead", "principal", "staff"):
        anchor = matched[0] if matched else (cv.skills[0] if cv.skills else "your stack")
        qs.append(InterviewQuestion(category="system_design",
            question=(f"Design a system for a core responsibility of this role using {anchor}. Walk through "
                      f"the data model, how you'd scale it, and how you'd handle failure.")))

    # Ensure a reasonable minimum.
    if len(qs) < 5:
        for s in (cv.skills or ["your core stack"])[:3]:
            qs.append(InterviewQuestion(category="technical",
                question=f"Describe a challenging problem you solved using {s} and what you learned."))

    # De-dupe by question text, keep order.
    seen, out = set(), []
    for q in qs:
        if q.question not in seen:
            seen.add(q.question)
            out.append(q)
    return out[:10]


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
