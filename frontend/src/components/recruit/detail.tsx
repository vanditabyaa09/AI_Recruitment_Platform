"use client";

import { useEffect, useState } from "react";
import { api, CandidateDetail, InterviewQuestion } from "@/lib/api";
import { ScoreRing, ScoreBar, SkillChip, RecommendationBadge, GemBadge } from "./ui-bits";
import { Button } from "@/components/ui/button";

const Q_LABEL: Record<string, string> = {
  technical: "Technical",
  behavioral: "Behavioral",
  gap_probing: "Gap Probing",
  project_deep_dive: "Project Deep-Dive",
  soft_skills: "Soft Skills",
};

export function CandidateView({ id, onBack }: { id: string; onBack: () => void }) {
  const [data, setData] = useState<CandidateDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [questions, setQuestions] = useState<InterviewQuestion[]>([]);
  const [qLoading, setQLoading] = useState(false);
  const [qError, setQError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    api.candidate(id)
      .then((d) => {
        if (!active) return;
        setData(d);
        setQuestions(d.interview_questions || []);
        setLoading(false);
      })
      .catch(() => active && setLoading(false));
    return () => { active = false; };
  }, [id]);

  const genQuestions = async () => {
    setQLoading(true);
    setQError("");
    try {
      setQuestions(await api.generateQuestions(id));
    } catch (e) {
      setQError(e instanceof Error ? e.message : "Failed to generate questions");
    } finally {
      setQLoading(false);
    }
  };

  if (loading || !data) {
    return (
      <div>
        <BackButton onBack={onBack} />
        <div className="surface flex h-64 items-center justify-center text-muted">Loading candidate…</div>
      </div>
    );
  }

  const p = data.parsed;

  return (
    <div className="space-y-6 animate-fade-up">
      <BackButton onBack={onBack} />

      {/* header */}
      <div className="surface p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-4">
            <ScoreRing score={data.scores.overall} size={68} />
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-2xl font-semibold">{p.name}</h1>
                {data.is_hidden_gem && <GemBadge />}
              </div>
              <p className="mt-0.5 max-w-xl text-sm text-muted">{p.headline || `Rank #${data.rank}`}</p>
              <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-faint">
                <span>Rank #{data.rank}</span>
                <span>·</span>
                <span>{p.years_of_experience}y experience</span>
                {p.location && <><span>·</span><span>{p.location}</span></>}
                {p.email && <><span>·</span><span>{p.email}</span></>}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <RecommendationBadge rec={data.explanation.recommendation} />
            <a href={api.pdfUrl(data.id)} target="_blank" rel="noreferrer">
              <Button variant="secondary" size="sm">Export PDF</Button>
            </a>
          </div>
        </div>
      </div>

      {/* score breakdown */}
      <div className="surface p-6">
        <h2 className="mb-4 text-sm font-semibold">Score breakdown</h2>
        <div className="grid gap-x-8 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
          <ScoreBar label="Skills" value={data.scores.skills} />
          <ScoreBar label="Experience" value={data.scores.experience} />
          <ScoreBar label="Semantic fit" value={data.scores.semantic} />
          <ScoreBar label="Domain" value={data.scores.domain} />
          <ScoreBar label="Education" value={data.scores.education} />
          <ScoreBar label="Soft skills" value={data.scores.soft_skills} />
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* left: explanation */}
        <div className="space-y-6 lg:col-span-2">
          <div className="surface p-6">
            <h2 className="mb-2 text-sm font-semibold">Why this ranking</h2>
            <p className="text-sm leading-relaxed text-fg/90">{data.explanation.summary}</p>
            <div className="mt-5 grid gap-5 sm:grid-cols-2">
              <div>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">Strengths</h3>
                <ul className="space-y-1.5">
                  {data.explanation.strengths.map((s, i) => (
                    <li key={i} className="flex gap-2 text-sm text-fg/90"><span className="text-success">+</span>{s}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">Gaps &amp; risks</h3>
                <ul className="space-y-1.5">
                  {[...data.explanation.gaps, ...data.explanation.flags].map((s, i) => (
                    <li key={i} className="flex gap-2 text-sm text-fg/90"><span className="text-warn">!</span>{s}</li>
                  ))}
                  {!data.explanation.gaps.length && !data.explanation.flags.length && (
                    <li className="text-sm text-faint">No significant gaps identified.</li>
                  )}
                </ul>
              </div>
            </div>
          </div>

          {/* interview questions — generated on demand */}
          <div className="surface p-6">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold">Tailored interview questions</h2>
              {questions.length > 0 && (
                <Button variant="ghost" size="sm" onClick={genQuestions} disabled={qLoading}>
                  {qLoading ? "Regenerating…" : "Regenerate"}
                </Button>
              )}
            </div>

            {questions.length === 0 ? (
              <div className="rounded-lg border border-dashed border-line bg-surface/40 p-6 text-center">
                <p className="text-sm text-muted">
                  Generate interview questions tailored to {p.name.split(" ")[0]}&apos;s background, skills, and gaps.
                </p>
                <Button className="mt-3" size="sm" onClick={genQuestions} disabled={qLoading}>
                  {qLoading ? "Generating…" : "Generate interview questions"}
                </Button>
                {qError && <p className="mt-2 text-xs text-danger">{qError}</p>}
              </div>
            ) : (
              <div className="space-y-2.5">
                {questions.map((q, i) => (
                  <div key={i} className="rounded-lg border border-line bg-surface/60 p-3">
                    <span className="label !text-accent">{Q_LABEL[q.category] || q.category}</span>
                    <p className="mt-1 text-sm text-fg/90">{q.question}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* right: profile */}
        <div className="space-y-6">
          <div className="surface p-6">
            <h2 className="mb-3 text-sm font-semibold">Skills</h2>
            <div className="flex flex-wrap gap-1.5">
              {data.matched_skills.map((s) => <SkillChip key={s} skill={s} matched />)}
              {p.skills
                .filter((s) => !data.matched_skills.map((m) => m.toLowerCase()).includes(s.toLowerCase()))
                .map((s) => <SkillChip key={s} skill={s} />)}
            </div>
            {data.missing_skills.length > 0 && (
              <p className="mt-3 text-xs text-muted">
                Missing must-haves: <span className="text-danger">{data.missing_skills.join(", ")}</span>
              </p>
            )}
          </div>

          {p.experience.length > 0 && (
            <div className="surface p-6">
              <h2 className="mb-3 text-sm font-semibold">Experience</h2>
              <div className="space-y-2.5">
                {p.experience.slice(0, 5).map((x, i) => (
                  <div key={i} className="text-sm">
                    <div className="font-medium">{x.role || "Role"}</div>
                    {x.company && <div className="text-muted">{x.company}</div>}
                    {(x.start || x.end) && <div className="text-xs text-faint">{x.start}{x.end ? `–${x.end}` : ""}</div>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {p.education.length > 0 && (
            <div className="surface p-6">
              <h2 className="mb-3 text-sm font-semibold">Education</h2>
              <div className="space-y-2">
                {p.education.map((e, i) => (
                  <div key={i} className="text-sm">
                    <div className="font-medium">{[e.degree, e.field].filter(Boolean).join(", ") || "Degree"}</div>
                    {e.institution && <div className="text-muted">{e.institution}</div>}
                    {e.year && <div className="text-xs text-faint">{e.year}</div>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {p.certifications.length > 0 && (
            <div className="surface p-6">
              <h2 className="mb-3 text-sm font-semibold">Certifications</h2>
              <div className="flex flex-wrap gap-1.5">
                {p.certifications.map((c) => <SkillChip key={c} skill={c} />)}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function BackButton({ onBack }: { onBack: () => void }) {
  return (
    <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-fg">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M15 18l-6-6 6-6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      Back to results
    </button>
  );
}
