// API client for the RecruitIQ backend.
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---- Types (mirror backend/app/schemas.py) ----
export interface ParsedJD {
  role: string;
  seniority: string;
  experience_required: string;
  min_years: number;
  hard_skills: string[];
  soft_skills: string[];
  must_have: string[];
  nice_to_have: string[];
  domain_knowledge: string[];
  education_requirements: string[];
  responsibilities: string[];
}

export interface JDResponse {
  id: string;
  title: string;
  parsed: ParsedJD;
  confidence: Record<string, number>;
}

export interface JobStatus {
  id: string;
  jd_id: string;
  status: "pending" | "parsing" | "ranking" | "explaining" | "done" | "failed";
  progress: number;
  total: number;
  processed: number;
  message: string;
  elapsed_seconds: number;
  using_ai: boolean;
}

export interface CandidateSummary {
  id: string;
  rank: number;
  name: string;
  headline: string;
  overall: number;
  years_of_experience: number;
  top_skills: string[];
  recommendation: string;
  is_hidden_gem: boolean;
  summary: string;
}

export interface ScoreBreakdown {
  overall: number;
  skills: number;
  experience: number;
  domain: number;
  education: number;
  soft_skills: number;
  semantic: number;
}

export interface Explanation {
  summary: string;
  strengths: string[];
  gaps: string[];
  flags: string[];
  recommendation: string;
}

export interface InterviewQuestion {
  category: string;
  question: string;
}

export interface EducationItem {
  institution: string;
  degree: string;
  field: string;
  year: string;
}

export interface ExperienceItem {
  company: string;
  role: string;
  start: string;
  end: string;
  highlights: string[];
}

export interface ParsedCV {
  name: string;
  email: string | null;
  phone: string | null;
  location: string | null;
  headline: string;
  years_of_experience: number;
  skills: string[];
  education: EducationItem[];
  certifications: string[];
  experience: ExperienceItem[];
  projects: { name?: string; description?: string }[];
  achievements: string[];
}

export interface CandidateDetail {
  id: string;
  rank: number;
  parsed: ParsedCV;
  scores: ScoreBreakdown;
  explanation: Explanation;
  matched_skills: string[];
  missing_skills: string[];
  interview_questions: InterviewQuestion[];
  is_hidden_gem: boolean;
}

export interface DiversityFlag {
  severity: "info" | "warning";
  title: string;
  detail: string;
}

export interface DiversityReport {
  skewed: boolean;
  flags: DiversityFlag[];
  hidden_gems: CandidateSummary[];
  shortlist_size: number;
  distribution: {
    education?: Record<string, number>;
    experience?: Record<string, number>;
    score_bands?: Record<string, number>;
  };
}

export interface ResultsResponse {
  job_id: string;
  jd: JDResponse;
  candidates: CandidateSummary[];
  diversity: DiversityReport;
  using_ai: boolean;
  elapsed_seconds: number;
}

// ---- helpers ----
async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : "Request failed");
  }
  return res.json();
}

// ---- endpoints ----
export const api = {
  base: BASE,

  async health() {
    return jsonOrThrow<{ status: string; ai: boolean; model: string }>(
      await fetch(`${BASE}/health`),
    );
  },

  async parseJDText(text: string) {
    return jsonOrThrow<JDResponse>(
      await fetch(`${BASE}/api/jd/text`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      }),
    );
  },

  async parseJDFile(file: File) {
    const fd = new FormData();
    fd.append("file", file);
    return jsonOrThrow<JDResponse>(
      await fetch(`${BASE}/api/jd`, { method: "POST", body: fd }),
    );
  },

  async screen(jdId: string, files: File[]) {
    const fd = new FormData();
    fd.append("jd_id", jdId);
    files.forEach((f) => fd.append("files", f));
    return jsonOrThrow<{ job_id: string; total: number }>(
      await fetch(`${BASE}/api/screen`, { method: "POST", body: fd }),
    );
  },

  async jobStatus(jobId: string) {
    return jsonOrThrow<JobStatus>(await fetch(`${BASE}/api/jobs/${jobId}`));
  },

  async results(jobId: string) {
    return jsonOrThrow<ResultsResponse>(await fetch(`${BASE}/api/results/${jobId}`));
  },

  async candidate(id: string) {
    return jsonOrThrow<CandidateDetail>(await fetch(`${BASE}/api/candidates/${id}`));
  },

  async chat(jobId: string, message: string) {
    return jsonOrThrow<{ response: string }>(
      await fetch(`${BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId, message }),
      }),
    );
  },

  async compare(jobId: string, candidateIds: string[]) {
    return jsonOrThrow<CandidateDetail[]>(
      await fetch(`${BASE}/api/compare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId, candidate_ids: candidateIds }),
      }),
    );
  },

  csvUrl(jobId: string) {
    return `${BASE}/api/export/csv/${jobId}`;
  },

  pdfUrl(candidateId: string) {
    return `${BASE}/api/export/pdf/${candidateId}`;
  },
};
