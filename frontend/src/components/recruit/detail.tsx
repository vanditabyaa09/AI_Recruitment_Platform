"use client";

import { useEffect, useState } from "react";
import { api, CandidateDetail } from "@/lib/api";
import { ScoreRing, ScoreBar, SkillChip, RecommendationBadge, GemBadge } from "./ui-bits";
import { Button } from "@/components/ui/button";

const Q_LABEL: Record<string, string> = {
  technical: "Technical",
  behavioral: "Behavioral",
  gap_probing: "Gap Probing",
  project_deep_dive: "Project Deep-Dive",
  soft_skills: "Soft Skills",
};

export function CandidateDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const [data, setData] = useState<CandidateDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    api.candidate(id).then((d) => { if (active) { setData(d); setLoading(false); } }).catch(() => active && setLoading(false));
    return () => { active = false; };
  }, [id]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm animate-fade-up" onClick={onClose} />
      <div className="relative h-full w-full max-w-2xl overflow-y-auto border-l border-line bg-bg shadow-2xl animate-fade-up">
        {loading || !data ? (
          <div className="flex h-full items-center justify-center text-muted">Loading candidate…</div>
        ) : (
          <div className="p-6 sm:p-8">
            {/* header */}
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-center gap-4">
                <ScoreRing score={data.scores.overall} size={64} />
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-xl font-semibold">{data.parsed.name}</h2>
                    {data.is_hidden_gem && <GemBadge />}
                  </div>
                  <p className="mt-0.5 text-sm text-muted">{data.parsed.headline || `Rank #${data.rank}`}</p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-faint">
                    <span>Rank #{data.rank}</span>
                    <span>·</span>
                    <span>{data.parsed.years_of_experience}y experience</span>
                    {data.parsed.location && <><span>·</span><span>{data.parsed.location}</span></>}
                  </div>
                </div>
              </div>
              <button onClick={onClose} className="rounded-lg p-1.5 text-faint hover:bg-elevated hover:text-fg">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12" strokeLinecap="round" /></svg>
              </button>
            </div>

            <div className="mt-3 flex items-center gap-2">
              <RecommendationBadge rec={data.explanation.recommendation} />
              <a href={api.pdfUrl(data.id)} target="_blank" rel="noreferrer">
                <Button variant="secondary" size="sm">Export PDF</Button>
              </a>
            </div>

            {/* score breakdown */}
            <div className="mt-6 grid grid-cols-2 gap-x-6 gap-y-3 rounded-xl border border-line bg-surface/60 p-4">
              <ScoreBar label="Skills" value={data.scores.skills} />
              <ScoreBar label="Experience" value={data.scores.experience} />
              <ScoreBar label="Semantic fit" value={data.scores.semantic} />
              <ScoreBar label="Domain" value={data.scores.domain} />
              <ScoreBar label="Education" value={data.scores.education} />
              <ScoreBar label="Soft skills" value={data.scores.soft_skills} />
            </div>

            {/* why this ranking */}
            <Section title="Why this ranking">
              <p className="text-sm leading-relaxed text-fg/90">{data.explanation.summary}</p>
            </Section>

            <div className="grid gap-4 sm:grid-cols-2">
              <Section title="Strengths">
                <ul className="space-y-1.5">
                  {data.explanation.strengths.map((s, i) => (
                    <li key={i} className="flex gap-2 text-sm text-fg/90"><span className="text-success">+</span>{s}</li>
                  ))}
                </ul>
              </Section>
              <Section title="Gaps & risks">
                <ul className="space-y-1.5">
                  {[...data.explanation.gaps, ...data.explanation.flags].map((s, i) => (
                    <li key={i} className="flex gap-2 text-sm text-fg/90"><span className="text-warn">!</span>{s}</li>
                  ))}
                  {!data.explanation.gaps.length && !data.explanation.flags.length && (
                    <li className="text-sm text-faint">No significant gaps identified.</li>
                  )}
                </ul>
              </Section>
            </div>

            {/* skills */}
            <Section title="Skills">
              <div className="flex flex-wrap gap-1.5">
                {data.matched_skills.map((s) => <SkillChip key={s} skill={s} matched />)}
                {data.parsed.skills.filter((s) => !data.matched_skills.map((m) => m.toLowerCase()).includes(s.toLowerCase())).map((s) => <SkillChip key={s} skill={s} />)}
              </div>
              {data.missing_skills.length > 0 && (
                <p className="mt-2 text-xs text-muted">Missing must-haves: <span className="text-danger">{data.missing_skills.join(", ")}</span></p>
              )}
            </Section>

            {/* experience */}
            {data.parsed.experience.length > 0 && (
              <Section title="Experience">
                <div className="space-y-2">
                  {data.parsed.experience.slice(0, 4).map((x, i) => (
                    <div key={i} className="text-sm">
                      <span className="font-medium">{x.role || "Role"}</span>
                      {x.company && <span className="text-muted"> · {x.company}</span>}
                      {(x.start || x.end) && <span className="text-faint"> ({x.start}{x.end ? `–${x.end}` : ""})</span>}
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* interview questions */}
            <Section title="Tailored interview questions">
              <div className="space-y-2.5">
                {data.interview_questions.map((q, i) => (
                  <div key={i} className="rounded-lg border border-line bg-surface/60 p-3">
                    <span className="label !text-accent">{Q_LABEL[q.category] || q.category}</span>
                    <p className="mt-1 text-sm text-fg/90">{q.question}</p>
                  </div>
                ))}
              </div>
            </Section>
          </div>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-6">
      <h3 className="mb-2 text-sm font-semibold text-fg">{title}</h3>
      {children}
    </div>
  );
}
