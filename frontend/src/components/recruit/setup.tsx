"use client";

import { useState, useRef, useCallback } from "react";
import { api, JDResponse } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { SkillChip } from "./ui-bits";
import { cn } from "@/lib/utils";

const SAMPLE_JD = `Senior Backend Engineer

About the Role:
We are looking for a Senior Backend Engineer to join our platform team. You will design and build scalable microservices, work with cloud infrastructure, and mentor junior developers.

Requirements:
- 5+ years of professional software development experience
- Strong proficiency in Python and FastAPI
- Experience with PostgreSQL and database design
- AWS cloud services (EC2, S3, Lambda)
- Docker and containerization
- RESTful API design

Nice to Have:
- Kubernetes orchestration experience
- Machine learning pipeline integration
- GraphQL APIs

Soft Skills:
- Strong communication and teamwork
- Problem solving and analytical thinking
- Leadership and mentoring

Education:
- Bachelor's degree in Computer Science or related field`;

interface Props {
  onRun: (jd: JDResponse, files: File[]) => void;
  aiEnabled: boolean | null;
  model: string;
}

export function Setup({ onRun, aiEnabled, model }: Props) {
  const [jdText, setJdText] = useState("");
  const [jd, setJd] = useState<JDResponse | null>(null);
  const [parsing, setParsing] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [loadingSamples, setLoadingSamples] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const parseJD = useCallback(async () => {
    const text = jdText.trim();
    if (!text) return;
    setParsing(true);
    setError("");
    try {
      setJd(await api.parseJDText(text));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to parse job description");
    } finally {
      setParsing(false);
    }
  }, [jdText]);

  const addFiles = (incoming: FileList | File[]) => {
    const arr = Array.from(incoming).filter((f) => /\.(pdf|docx?|txt|md)$/i.test(f.name));
    setFiles((prev) => {
      const names = new Set(prev.map((f) => f.name));
      return [...prev, ...arr.filter((f) => !names.has(f.name))];
    });
  };

  const loadSamples = async () => {
    setLoadingSamples(true);
    setError("");
    try {
      if (!jd) {
        setJdText(SAMPLE_JD);
        setJd(await api.parseJDText(SAMPLE_JD));
      }
      const manifest = await fetch("/samples/manifest.json").then((r) => r.json());
      const loaded: File[] = await Promise.all(
        (manifest.cvs as string[]).map(async (name) => {
          const text = await fetch(`/samples/cvs/${name}`).then((r) => r.text());
          return new File([text], name, { type: "text/plain" });
        }),
      );
      setFiles(loaded);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load sample data");
    } finally {
      setLoadingSamples(false);
    }
  };

  const p = jd?.parsed;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {/* ---- Job description ---- */}
      <section className="surface flex flex-col p-6">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <span className="label">Step 1</span>
            <h2 className="mt-1 text-lg font-semibold">Job Description</h2>
          </div>
          <button onClick={() => setJdText(SAMPLE_JD)} className="text-xs font-medium text-accent hover:underline">
            Use sample
          </button>
        </div>

        <textarea
          value={jdText}
          onChange={(e) => { setJdText(e.target.value); setJd(null); }}
          placeholder="Paste the full job description here — requirements, responsibilities, must-haves…"
          className="min-h-[200px] flex-1 resize-none rounded-lg border border-line bg-surface p-3 text-sm text-fg placeholder:text-faint focus:border-accent focus:outline-none"
        />

        <div className="mt-3 flex items-center gap-3">
          <Button onClick={parseJD} disabled={!jdText.trim() || parsing} size="sm">
            {parsing ? "Parsing…" : jd ? "Re-parse" : "Parse requirements"}
          </Button>
          {jd && <span className="text-xs text-success">✓ Parsed</span>}
        </div>

        {p && (
          <div className="mt-4 space-y-3 rounded-lg border border-line bg-surface/60 p-4 animate-fade-up">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold">{p.role || "Role"}</span>
              <span className="rounded-md bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent">{p.seniority}</span>
              <span className="text-xs text-muted">{p.experience_required}</span>
            </div>
            <div>
              <span className="label">Must have</span>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {p.must_have.length ? p.must_have.map((s) => <SkillChip key={s} skill={s} matched />) : <span className="text-xs text-faint">—</span>}
              </div>
            </div>
            <div>
              <span className="label">Nice to have</span>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {p.nice_to_have.length ? p.nice_to_have.map((s) => <SkillChip key={s} skill={s} />) : <span className="text-xs text-faint">—</span>}
              </div>
            </div>
            {p.soft_skills.length > 0 && (
              <div>
                <span className="label">Soft skills</span>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {p.soft_skills.map((s) => <SkillChip key={s} skill={s} />)}
                </div>
              </div>
            )}
            {p.domain_knowledge.length > 0 && (
              <div>
                <span className="label">Domain knowledge</span>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {p.domain_knowledge.map((s) => <SkillChip key={s} skill={s} />)}
                </div>
              </div>
            )}
            {p.education_requirements.length > 0 && (
              <div>
                <span className="label">Education</span>
                <p className="mt-1 text-xs text-muted">{p.education_requirements.join("; ")}</p>
              </div>
            )}
          </div>
        )}
      </section>

      {/* ---- CVs ---- */}
      <section className="surface flex flex-col p-6">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <span className="label">Step 2</span>
            <h2 className="mt-1 text-lg font-semibold">Candidate CVs</h2>
          </div>
          <button onClick={loadSamples} disabled={loadingSamples} className="text-xs font-medium text-accent hover:underline disabled:opacity-50">
            {loadingSamples ? "Loading…" : "Load 25 sample CVs"}
          </button>
        </div>

        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); }}
          onClick={() => fileInput.current?.click()}
          className={cn(
            "flex min-h-[200px] flex-1 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 text-center transition-colors",
            dragging ? "border-accent bg-accent-soft/40" : "border-line hover:border-line-strong",
          )}
        >
          <input
            ref={fileInput} type="file" multiple accept=".pdf,.docx,.doc,.txt,.md"
            className="hidden" onChange={(e) => e.target.files && addFiles(e.target.files)}
          />
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="mb-3 text-faint">
            <path d="M12 16V4m0 0L8 8m4-4l4 4" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M4 17v1a3 3 0 003 3h10a3 3 0 003-3v-1" strokeLinecap="round" />
          </svg>
          <p className="text-sm font-medium">Drop CVs here or click to browse</p>
          <p className="mt-1 text-xs text-faint">PDF, DOCX, or TXT — batch upload supported</p>
        </div>

        {files.length > 0 && (
          <div className="mt-3 flex items-center justify-between">
            <span className="text-xs text-muted">
              <span className="num font-semibold text-fg">{files.length}</span> CV{files.length === 1 ? "" : "s"} ready
            </span>
            <button onClick={() => setFiles([])} className="text-xs text-faint hover:text-danger">Clear</button>
          </div>
        )}
      </section>

      {/* ---- Run bar (spans both) ---- */}
      <div className="lg:col-span-2">
        {error && <p className="mb-3 rounded-lg bg-danger-soft px-4 py-2 text-sm text-danger">{error}</p>}
        <div className="surface flex flex-col items-center justify-between gap-4 p-5 sm:flex-row">
          <div className="text-sm text-muted">
            {jd && files.length
              ? <>Ready to screen <span className="num font-semibold text-fg">{files.length}</span> candidates against <span className="font-medium text-fg">{p?.role}</span>.</>
              : "Add a parsed job description and at least one CV to begin."}
            {aiEnabled === false && <span className="ml-2 text-warn">· offline heuristic mode</span>}
            {aiEnabled && <span className="ml-2 text-faint">· {model}</span>}
          </div>
          <Button
            size="lg"
            disabled={!jd || files.length === 0}
            onClick={() => jd && onRun(jd, files)}
          >
            Screen candidates →
          </Button>
        </div>
      </div>
    </div>
  );
}
