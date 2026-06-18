import json
import hashlib
import numpy as np
from openai import AsyncOpenAI

from app.config import get_settings
from app.schemas import ParsedJD, ParsedCV, ScoreBreakdown, Explanation

settings = get_settings()

# Cap output tokens so completions can't ramble and inflate cost.
MAX_OUTPUT_TOKENS = 700
# Trim parser inputs — most JDs/CVs fit comfortably within this.
MAX_INPUT_CHARS = 8000


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


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
        # Content-hash caches so repeated/identical inputs cost zero tokens
        # (e.g. re-ranking the same pool, re-uploading the same CV).
        self._embedding_cache: dict[str, list[float]] = {}
        self._parse_cache: dict[str, dict] = {}

    async def get_embedding(self, text: str) -> list[float]:
        key = _hash(text)
        if key in self._embedding_cache:
            return self._embedding_cache[key]
        if settings.use_mock_ai or not self.client:
            emb = _mock_embedding(text)
        else:
            try:
                response = await self.client.embeddings.create(
                    model=settings.embedding_model,
                    input=text[:MAX_INPUT_CHARS],
                )
                emb = response.data[0].embedding
            except Exception:
                emb = _mock_embedding(text)
        self._embedding_cache[key] = emb
        return emb

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Batch-embed multiple texts in a single request. Cached texts are
        served from cache and only the misses are sent to the API."""
        if not texts:
            return []
        results: list[list[float] | None] = [None] * len(texts)
        miss_idx, miss_texts = [], []
        for i, t in enumerate(texts):
            cached = self._embedding_cache.get(_hash(t))
            if cached is not None:
                results[i] = cached
            else:
                miss_idx.append(i)
                miss_texts.append(t)

        if miss_texts:
            if settings.use_mock_ai or not self.client:
                embs = [_mock_embedding(t) for t in miss_texts]
            else:
                try:
                    response = await self.client.embeddings.create(
                        model=settings.embedding_model,
                        input=[t[:MAX_INPUT_CHARS] for t in miss_texts],
                    )
                    embs = [item.embedding for item in response.data]
                except Exception:
                    embs = [_mock_embedding(t) for t in miss_texts]
            for i, t, emb in zip(miss_idx, miss_texts, embs):
                self._embedding_cache[_hash(t)] = emb
                results[i] = emb

        return [r for r in results]  # all slots filled

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
                max_tokens=MAX_OUTPUT_TOKENS,
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
                max_tokens=MAX_OUTPUT_TOKENS,
            )
            return response.choices[0].message.content or ""
        except Exception:
            return ""

    async def parse_job_description(self, text: str) -> tuple[ParsedJD, dict]:
        system = """You are an expert HR analyst. Extract structured job description data.
Return JSON with keys: role, seniority, experience_required, hard_skills, soft_skills,
must_have, nice_to_have, domain_knowledge, education_requirements, confidence_scores.
confidence_scores should be a dict mapping each field to a 0-1 confidence value."""
        data = await self._chat_json(system, text[:MAX_INPUT_CHARS])
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
        key = _hash(text)
        if key in self._parse_cache:
            return ParsedCV.model_validate(self._parse_cache[key])
        data = await self._chat_json(system, text[:MAX_INPUT_CHARS])
        if not data:
            data = self._mock_parse_cv(text)
        self._parse_cache[key] = data
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

    def local_explanation(self, jd: ParsedJD, cv: ParsedCV, scores: ScoreBreakdown) -> Explanation:
        """Token-free, rule-based fit analysis. Used for the long tail of
        candidates we don't surface, and as a fallback when the LLM is off."""
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
        return Explanation(
            strengths=strengths,
            gaps=gaps,
            risks=["Limited exposure to some preferred qualifications"] if gaps else [],
            potential=["Shows growth trajectory in technical roles"],
            summary=summary,
        )

    def local_interview_questions(self, jd: ParsedJD, cv: ParsedCV) -> list[dict]:
        """Token-free, rule-based interview questions (fallback path)."""
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

    async def generate_explanation(self, jd: ParsedJD, cv: ParsedCV, scores: ScoreBreakdown) -> Explanation:
        system = "You are a recruiter AI. Generate candidate fit analysis as JSON with keys: strengths, gaps, risks, potential (all lists), summary (string)."
        user = f"JD: {jd.model_dump_json()}\nCV: {cv.model_dump_json()}\nScores: {scores.model_dump_json()}"
        data = await self._chat_json(system, user)
        if not data:
            return self.local_explanation(jd, cv, scores)
        return Explanation(**data)

    async def analyze_candidate(self, jd: ParsedJD, cv: ParsedCV, scores: ScoreBreakdown) -> tuple[Explanation, list[dict]]:
        """Single LLM call producing BOTH the fit explanation and tailored
        interview questions — halves per-candidate calls for the shortlist."""
        system = """You are a recruiter AI. Return JSON with keys:
explanation: {strengths, gaps, risks, potential (all lists of strings), summary (string)}
questions: list of {category: 'technical'|'behavioral'|'gap_probing'|'project_deep_dive', question: string}.
Questions MUST reference specific CV content. No generic questions."""
        user = f"JD: {jd.model_dump_json()}\nCV: {cv.model_dump_json()}\nScores: {scores.model_dump_json()}"
        data = await self._chat_json(system, user)
        if not data or "explanation" not in data:
            return self.local_explanation(jd, cv, scores), self.local_interview_questions(jd, cv)
        explanation = Explanation(**data["explanation"])
        questions = data.get("questions") or self.local_interview_questions(jd, cv)
        return explanation, questions

    async def generate_interview_questions(self, jd: ParsedJD, cv: ParsedCV) -> list[dict]:
        system = """Generate personalized interview questions as JSON with key 'questions' containing list of
{category: 'technical'|'behavioral'|'gap_probing'|'project_deep_dive', question: string}.
Questions MUST reference specific CV content. No generic questions."""
        user = f"JD: {jd.model_dump_json()}\nCV: {cv.model_dump_json()}"
        data = await self._chat_json(system, user)
        if not data or "questions" not in data:
            return self.local_interview_questions(jd, cv)
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
