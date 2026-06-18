const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}/api/v1${endpoint}`, {
    ...options,
    headers: {
      ...(options?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const errorText = await res.text();
    let message = errorText || `API error: ${res.status}`;
    try {
      const parsed = JSON.parse(errorText) as { detail?: string | { msg: string }[] };
      if (typeof parsed.detail === "string") {
        message = parsed.detail;
      } else if (Array.isArray(parsed.detail)) {
        message = parsed.detail.map((d) => d.msg).join(", ");
      }
    } catch {
      /* use raw error text */
    }
    throw new Error(message);
  }
  const contentType = res.headers.get("content-type");
  if (contentType?.includes("application/json")) {
    return res.json();
  }
  return res as unknown as T;
}

export interface JobDescription {
  id: string;
  title: string;
  parsed_data: Record<string, unknown>;
  confidence_scores: Record<string, number>;
  created_at: string;
}

export interface CandidateListItem {
  id: string;
  rank: number | null;
  name: string;
  overall_score: number;
  years_of_experience: number;
  top_skills: string[];
  status: string;
  is_hidden_gem: boolean;
}

export interface CandidateDetail {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  location: string | null;
  parsed_data: Record<string, unknown>;
  years_of_experience: number;
  rank: number | null;
  is_hidden_gem: boolean;
  scores: {
    overall_score: number;
    skill_score: number;
    experience_score: number;
    domain_score: number;
    education_score: number;
    soft_skill_score: number;
  } | null;
  explanation: {
    strengths: string[];
    gaps: string[];
    risks: string[];
    potential: string[];
    summary: string;
  } | null;
  executive_summary: string | null;
  skills: string[];
  experiences: { company: string; role: string; start: string | null; end: string | null }[];
  interview_questions: { category: string; question: string }[];
}

export interface DiversityAlert {
  type: string;
  severity: string;
  title: string;
  message: string;
}

export interface Analytics {
  total_cvs: number;
  candidates_ranked: number;
  hidden_gems: number;
  diversity_alerts: number;
  diversity_alert_list: DiversityAlert[];
  score_distribution: { range: string; count: number }[];
  skill_heatmap: { skill: string; count: number }[];
  experience_distribution: { range: string; count: number }[];
  education_breakdown: { institution: string; count: number }[];
  hiring_funnel: { stage: string; count: number }[];
  diversity_insights: {
    education_breakdown?: { name: string; count: number }[];
    employer_breakdown?: { name: string; count: number }[];
    hidden_gem_count?: number;
  };
}

export interface ProcessingJob {
  id: string;
  job_type: string;
  status: string;
  progress: number;
  total_items: number;
  message: string | null;
}

export const api = {
  health: () => fetch(`${API_URL}/health`).then((r) => r.json()),

  uploadJD: async (file?: File, text?: string) => {
    const form = new FormData();
    if (file) form.append("file", file);
    if (text) form.append("text", text);
    return fetchAPI<JobDescription>("/upload-jd", { method: "POST", body: form });
  },

  uploadCVs: async (jobDescriptionId: string, files: File[]) => {
    const form = new FormData();
    form.append("job_description_id", jobDescriptionId);
    files.forEach((f) => form.append("files", f));
    return fetchAPI<{ job_id: string; message: string; total: number }>("/upload-cvs", {
      method: "POST",
      body: form,
    });
  },

  getProcessingStatus: (jobId: string) => fetchAPI<ProcessingJob>(`/processing/${jobId}`),

  rankCandidates: (jobDescriptionId: string) =>
    fetchAPI<{ job_id: string; message: string }>("/rank-candidates", {
      method: "POST",
      body: JSON.stringify({ job_description_id: jobDescriptionId }),
    }),

  listCandidates: (params: Record<string, string | number | boolean> = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => query.set(k, String(v)));
    return fetchAPI<{ items: CandidateListItem[]; total: number; page: number; page_size: number }>(
      `/candidates?${query}`
    );
  },

  getCandidate: (id: string) => fetchAPI<CandidateDetail>(`/candidate/${id}`),

  getAnalytics: (jobDescriptionId?: string) => {
    const q = jobDescriptionId ? `?job_description_id=${jobDescriptionId}` : "";
    return fetchAPI<Analytics>(`/analytics${q}`);
  },

  generateQuestions: (candidateId: string) =>
    fetchAPI<{ questions: { category: string; question: string }[] }>("/generate-questions", {
      method: "POST",
      body: JSON.stringify({ candidate_id: candidateId }),
    }),

  downloadReport: async (candidateId: string) => {
    const res = await fetch(`${API_URL}/api/v1/generate-report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ candidate_id: candidateId }),
    });
    return res.blob();
  },

  exportCSV: (jobDescriptionId?: string) => {
    const q = jobDescriptionId ? `?job_description_id=${jobDescriptionId}` : "";
    return `${API_URL}/api/v1/export/csv${q}`;
  },

  exportPDF: (jobDescriptionId?: string) => {
    const q = jobDescriptionId ? `?job_description_id=${jobDescriptionId}` : "";
    return `${API_URL}/api/v1/export/pdf${q}`;
  },

  chat: (message: string, sessionId: string, jobDescriptionId?: string) =>
    fetchAPI<{ response: string; session_id: string }>("/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        session_id: sessionId,
        job_description_id: jobDescriptionId || null,
      }),
    }),

  listJobDescriptions: () =>
    fetchAPI<{ id: string; title: string; created_at: string }[]>("/job-descriptions"),

  getJobDescription: (id: string) => fetchAPI<JobDescription>(`/job-description/${id}`),

  hiringRecommendation: (jobDescriptionId: string) =>
    fetchAPI<{
      summary: string;
      primary_recommendations: { name: string; score: number; rank: number; rationale: string }[];
      hidden_gems_to_consider: { name: string; score: number; rank: number }[];
      next_steps: string[];
    }>(`/hiring-recommendation?job_description_id=${jobDescriptionId}`, { method: "POST" }),

  compareCandidates: (candidateIds: string[], jobDescriptionId?: string) =>
    fetchAPI<{ candidates: ComparedCandidate[] }>("/compare", {
      method: "POST",
      body: JSON.stringify({ candidate_ids: candidateIds, job_description_id: jobDescriptionId }),
    }),
};

export interface ComparedCandidate {
  id: string;
  name: string;
  rank: number | null;
  scores: { overall: number; skill: number; experience: number };
  skills: string[];
  years_of_experience: number;
  is_hidden_gem: boolean;
}
