import json
import hashlib
import numpy as np
from openai import AsyncOpenAI

from app.config import get_settings
from app.schemas import ParsedJD, ParsedCV, ScoreBreakdown, Explanation

settings = get_settings()


def _mock_embedding(text: str) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    vec = np.frombuffer(h * 16, dtype=np.uint8).astype(np.float32)
    vec = (vec - vec.mean()) / (vec.std() + 1e-8)
    return vec.tolist()[:384]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a)
    vb = np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


class AIService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    async def get_embedding(self, text: str) -> list[float]:
        if settings.use_mock_ai or not self.client:
            return _mock_embedding(text)
        try:
            response = await self.client.embeddings.create(
                model=settings.embedding_model,
                input=text[:8000],
            )
            return response.data[0].embedding
        except Exception:
            return _mock_embedding(text)

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Batch-embed multiple texts in a single request (falls back per-text on error/mock)."""
        if not texts:
            return []
        if settings.use_mock_ai or not self.client:
            return [_mock_embedding(t) for t in texts]
        try:
            response = await self.client.embeddings.create(
                model=settings.embedding_model,
                input=[t[:8000] for t in texts],
            )
            return [item.embedding for item in response.data]
        except Exception:
            return [_mock_embedding(t) for t in texts]

    async def _chat_json(self, system: str, user: str) -> dict:
        if settings.use_mock_ai or not self.client:
            return {}
        try:
            response = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            return json.loads(response.choices[0].message.content or "{}")
        except Exception:
            return {}

    async def _chat_text(self, system: str, user: str) -> str:
        if settings.use_mock_ai or not self.client:
            return ""
        try:
            response = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.4,
            )
            return response.choices[0].message.content or ""
        except Exception:
            return ""

    async def parse_job_description(self, text: str) -> tuple[ParsedJD, dict]:
        system = """You are an expert HR analyst. Extract structured job description data.
Return JSON with keys: role, seniority, experience_required, hard_skills, soft_skills,
must_have, nice_to_have, domain_knowledge, education_requirements, confidence_scores.
confidence_scores should be a dict mapping each field to a 0-1 confidence value."""
        data = await self._chat_json(system, text[:12000])
        if not data:
            data = self._mock_parse_jd(text)
        confidence = data.pop("confidence_scores", {})
        parsed = ParsedJD(**{k: data.get(k, [] if k.endswith("skills") or k.endswith("have") or "requirements" in k or "knowledge" in k else "") for k in ParsedJD.model_fields})
        # Fix list fields
        for field in ["hard_skills", "soft_skills", "must_have", "nice_to_have", "domain_knowledge", "education_requirements"]:
            val = data.get(field, [])
            setattr(parsed, field, val if isinstance(val, list) else [val] if val else [])
        for field in ["role", "seniority", "experience_required"]:
            setattr(parsed, field, str(data.get(field, "")))
        if not confidence:
            confidence = {f: 0.85 for f in ParsedJD.model_fields}
        return parsed, confidence

    def _mock_parse_jd(self, text: str) -> dict:
        text_lower = text.lower()
        skills = []
        skill_keywords = ["python", "javascript", "react", "aws", "docker", "kubernetes", "sql", "java", "typescript", "node", "fastapi", "postgresql"]
        for sk in skill_keywords:
            if sk in text_lower:
                skills.append(sk.title() if sk != "aws" else "AWS")
        seniority = "Senior" if "senior" in text_lower else "Mid" if "mid" in text_lower else "Junior" if "junior" in text_lower else "Mid-Senior"
        return {
            "role": "Software Engineer" if "engineer" in text_lower else "Technical Role",
            "seniority": seniority,
            "experience_required": "3-5 years" if "3" in text_lower else "2+ years",
            "hard_skills": skills[:8] or ["Python", "SQL", "Git"],
            "soft_skills": ["Communication", "Teamwork", "Problem Solving"],
            "must_have": skills[:3] or ["Python", "SQL"],
            "nice_to_have": skills[3:6] or ["AWS", "Docker"],
            "domain_knowledge": ["Software Development"],
            "education_requirements": ["Bachelor's in Computer Science or related field"],
            "confidence_scores": {"role": 0.9, "hard_skills": 0.85},
        }

    async def parse_cv(self, text: str) -> ParsedCV:
        system = """Extract structured CV/resume data. Return JSON with:
name, email, phone, location, education (list of {institution, degree, year}),
certifications, skills, companies, projects (list of {name, description}),
years_of_experience (number), achievements, tenure_history (list of {company, role, start, end})."""
        data = await self._chat_json(system, text[:12000])
        if not data:
            data = self._mock_parse_cv(text)
        return ParsedCV.model_validate(data)

    def _mock_parse_cv(self, text: str) -> dict:
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        name = lines[0] if lines else "Unknown Candidate"
        text_lower = text.lower()
        skills = []
        skill_keywords = ["python", "javascript", "react", "aws", "docker", "kubernetes", "sql", "java", "typescript", "node", "fastapi", "postgresql", "machine learning", "data analysis"]
        for sk in skill_keywords:
            if sk in text_lower:
                skills.append(sk.title() if sk != "aws" else "AWS")
        import re
        email_match = re.search(r"[\w.-]+@[\w.-]+\.\w+", text)
        phone_match = re.search(r"\+?[\d\s()-]{10,}", text)
        years = 3.0
        exp_match = re.search(r"(\d+)\+?\s*years?", text_lower)
        if exp_match:
            years = float(exp_match.group(1))
        companies = []
        for line in lines[:30]:
            if any(kw in line.lower() for kw in ["inc", "corp", "ltd", "technologies", "systems"]):
                companies.append(line[:80])
        return {
            "name": name[:100],
            "email": email_match.group() if email_match else None,
            "phone": phone_match.group().strip() if phone_match else None,
            "location": None,
            "education": [{"institution": "University", "degree": "Bachelor's", "year": "2020"}],
            "certifications": [],
            "skills": skills[:15] or ["Python", "SQL"],
            "companies": companies[:5] or ["Tech Company"],
            "projects": [{"name": "Project", "description": "Built scalable application"}],
            "years_of_experience": years,
            "achievements": ["Delivered key projects on time"],
            "tenure_history": [{"company": c, "role": "Engineer", "start": "2020", "end": "Present"} for c in (companies[:2] or ["Tech Co"])],
        }

    async def compute_scores(self, jd: ParsedJD, cv: ParsedCV, jd_embedding: list[float], cv_embedding: list[float]) -> ScoreBreakdown:
        base_sim = cosine_similarity(jd_embedding, cv_embedding)
        base_sim = max(0, min(1, (base_sim + 1) / 2))

        jd_skills = set(s.lower() for s in jd.hard_skills + jd.must_have)
        cv_skills = set(s.lower() for s in cv.skills)
        skill_match = len(jd_skills & cv_skills) / max(len(jd_skills), 1) if jd_skills else base_sim

        exp_required = 3.0
        import re
        exp_str = jd.experience_required.lower()
        exp_match = re.search(r"(\d+)", exp_str)
        if exp_match:
            exp_required = float(exp_match.group(1))
        exp_score = min(1.0, cv.years_of_experience / max(exp_required, 1))

        domain_score = base_sim * 0.9 + 0.1
        edu_score = 0.7 if cv.education else 0.4
        soft_jd = set(s.lower() for s in jd.soft_skills)
        soft_cv = set(s.lower() for s in cv.skills if s.lower() in ["communication", "leadership", "teamwork", "problem solving"])
        soft_score = len(soft_jd & soft_cv) / max(len(soft_jd), 1) if soft_jd else 0.65

        overall = (
            0.40 * skill_match +
            0.25 * exp_score +
            0.15 * domain_score +
            0.10 * edu_score +
            0.10 * soft_score
        ) * 100

        return ScoreBreakdown(
            overall_score=round(overall, 1),
            skill_score=round(skill_match * 100, 1),
            experience_score=round(exp_score * 100, 1),
            domain_score=round(domain_score * 100, 1),
            education_score=round(edu_score * 100, 1),
            soft_skill_score=round(soft_score * 100, 1),
        )

    async def generate_explanation(self, jd: ParsedJD, cv: ParsedCV, scores: ScoreBreakdown) -> Explanation:
        system = "You are a recruiter AI. Generate candidate fit analysis as JSON with keys: strengths, gaps, risks, potential (all lists), summary (string)."
        user = f"JD: {jd.model_dump_json()}\nCV: {cv.model_dump_json()}\nScores: {scores.model_dump_json()}"
        data = await self._chat_json(system, user)
        if not data:
            missing = [s for s in jd.must_have if s.lower() not in [sk.lower() for sk in cv.skills]]
            strengths = [f"Strong {s} experience" for s in cv.skills[:3]]
            gaps = [f"Missing {m}" for m in missing[:3]]
            summary = (
                f"{cv.name} demonstrates {'strong' if scores.overall_score > 70 else 'moderate'} alignment "
                f"with {scores.overall_score:.0f}% overall match. "
                f"{cv.years_of_experience:.0f} years of experience with skills in {', '.join(cv.skills[:4])}."
            )
            if gaps:
                summary += f" Missing {gaps[0].replace('Missing ', '')} which is listed as a requirement."
            return Explanation(strengths=strengths, gaps=gaps, risks=["Limited exposure to some preferred qualifications"] if gaps else [], potential=["Shows growth trajectory in technical roles"], summary=summary)
        return Explanation(**data)

    async def generate_interview_questions(self, jd: ParsedJD, cv: ParsedCV) -> list[dict]:
        system = """Generate personalized interview questions as JSON with key 'questions' containing list of
{category: 'technical'|'behavioral'|'gap_probing'|'project_deep_dive', question: string}.
Questions MUST reference specific CV content. No generic questions."""
        user = f"JD: {jd.model_dump_json()}\nCV: {cv.model_dump_json()}"
        data = await self._chat_json(system, user)
        if not data or "questions" not in data:
            questions = []
            for proj in cv.projects[:2]:
                questions.append({"category": "project_deep_dive", "question": f"You mention {proj.get('name', 'a project')}. What architecture decisions helped maintain performance at scale?"})
            for skill in cv.skills[:2]:
                questions.append({"category": "technical", "question": f"Describe your experience with {skill} and a challenging problem you solved using it."})
            for gap in jd.must_have[:1]:
                if gap.lower() not in [s.lower() for s in cv.skills]:
                    questions.append({"category": "gap_probing", "question": f"The role requires {gap}. How would you approach building proficiency in this area?"})
            questions.append({"category": "behavioral", "question": f"Tell me about a time at {cv.companies[0] if cv.companies else 'your previous role'} when you had to collaborate across teams under pressure."})
            return questions
        return data["questions"]

    async def chat_response(self, message: str, context: str) -> str:
        system = "You are RecruitIQ Copilot, a recruiter assistant. Answer based on candidate data provided. Be concise and actionable."
        user = f"Context:\n{context}\n\nQuestion: {message}"
        response = await self._chat_text(system, user)
        if not response:
            return self._mock_chat(message, context)
        return response

    def _mock_chat(self, message: str, context: str) -> str:
        msg = message.lower()
        if "hidden gem" in msg:
            return "Based on the current pool, hidden gems are candidates scoring above 80 with non-traditional backgrounds but strong skill alignment. Check the Hidden Gems filter in the candidate table."
        if "python" in msg:
            return "The strongest Python candidates are ranked in the top 10 by overall score. Filter by skill 'Python' in the candidate table for the full list."
        if "aws" in msg and "lack" in msg:
            return "Several candidates in the pool lack AWS experience. Review the gap analysis on individual candidate profiles for specifics."
        if "recommend" in msg:
            return "Based on overall scores and skill alignment, I recommend proceeding with the top 3 ranked candidates for technical interviews, while keeping hidden gems in the pipeline for diversity of background."
        return "I can help you compare candidates, find hidden gems, identify skill gaps, and generate hiring recommendations. Try asking about specific skills or candidate comparisons."


ai_service = AIService()
