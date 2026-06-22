"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { api, JDResponse, JobStatus, ResultsResponse } from "@/lib/api";
import { Setup } from "@/components/recruit/setup";
import { Results } from "@/components/recruit/results";
import { CandidateView } from "@/components/recruit/detail";
import { Copilot } from "@/components/recruit/copilot";

type Stage = "setup" | "processing" | "results";

const STEPS = [
  { key: "parsing", label: "Reading & structuring CVs" },
  { key: "ranking", label: "Scoring semantic fit" },
  { key: "explaining", label: "Writing explanations & questions" },
  { key: "done", label: "Done" },
];

export default function Home() {
  const [stage, setStage] = useState<Stage>("setup");
  const [ai, setAi] = useState<{ enabled: boolean | null; model: string }>({ enabled: null, model: "" });
  const [job, setJob] = useState<JobStatus | null>(null);
  const [results, setResults] = useState<ResultsResponse | null>(null);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [copilot, setCopilot] = useState(false);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    api.health()
      .then((h) => setAi({ enabled: h.ai, model: h.model }))
      .catch(() => setAi({ enabled: false, model: "" }));
    return () => { if (pollRef.current) clearTimeout(pollRef.current); };
  }, []);

  const poll = useCallback((jobId: string) => {
    const tick = async () => {
      try {
        const status = await api.jobStatus(jobId);
        setJob(status);
        if (status.status === "done") {
          setResults(await api.results(jobId));
          setStage("results");
          return;
        }
        if (status.status === "failed") {
          setError(status.message || "Screening failed");
          return;
        }
        pollRef.current = setTimeout(tick, 1200);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Lost connection to the server");
      }
    };
    tick();
  }, []);

  const onRun = useCallback(async (jd: JDResponse, files: File[]) => {
    setError("");
    setStage("processing");
    setJob(null);
    try {
      const { job_id } = await api.screen(jd.id, files);
      poll(job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start screening");
      setStage("setup");
    }
  }, [poll]);

  const reset = () => {
    if (pollRef.current) clearTimeout(pollRef.current);
    setStage("setup");
    setResults(null);
    setJob(null);
    setError("");
  };

  return (
    <div className="min-h-screen">
      {/* header */}
      <header className="glass sticky top-0 z-40">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3.5">
          <button onClick={reset} className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-sm font-bold text-accent-fg">R</span>
            <div className="text-left">
              <div className="text-sm font-semibold leading-tight">RecruitIQ</div>
              <div className="text-[11px] leading-tight text-faint">AI-Augmented Recruitment</div>
            </div>
          </button>
          <div className="flex items-center gap-2 text-xs">
            {ai.enabled === true && (
              <span className="flex items-center gap-1.5 rounded-full bg-success-soft px-2.5 py-1 text-success">
                <span className="h-1.5 w-1.5 rounded-full bg-success" /> AI live · {ai.model}
              </span>
            )}
            {ai.enabled === false && (
              <span className="flex items-center gap-1.5 rounded-full bg-warn-soft px-2.5 py-1 text-warn">
                <span className="h-1.5 w-1.5 rounded-full bg-warn" /> Offline heuristic mode
              </span>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-5 py-8">
        {stage === "setup" && (
          <>
            <div className="mb-8 max-w-2xl">
              <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
                Screen 1,000 CVs. Surface the 10 who matter.
              </h1>
              <p className="mt-2 text-muted">
                Semantic ranking beyond keywords — with transparent explanations, bias flags, and tailored interview questions for every candidate.
              </p>
            </div>
            <Setup onRun={onRun} aiEnabled={ai.enabled} model={ai.model} />
          </>
        )}

        {stage === "processing" && <Processing job={job} error={error} onReset={reset} />}

        {stage === "results" && results && !selectedId && (
          <Results
            results={results}
            onSelect={setSelectedId}
            onCopilot={() => setCopilot(true)}
            onReset={reset}
          />
        )}

        {stage === "results" && results && selectedId && (
          <CandidateView id={selectedId} onBack={() => setSelectedId(null)} />
        )}
      </main>

      {copilot && results && <Copilot jobId={results.job_id} onClose={() => setCopilot(false)} />}
    </div>
  );
}

function Processing({ job, error, onReset }: { job: JobStatus | null; error: string; onReset: () => void }) {
  const current = job?.status ?? "parsing";
  const progress = job?.progress ?? 0;
  const activeIdx = STEPS.findIndex((s) => s.key === current);

  return (
    <div className="mx-auto max-w-lg pt-10">
      <div className="surface p-8">
        {error ? (
          <div className="text-center">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-danger-soft text-2xl text-danger">!</div>
            <h2 className="text-lg font-semibold">Screening failed</h2>
            <p className="mt-1 text-sm text-muted">{error}</p>
            <button onClick={onReset} className="mt-4 text-sm font-medium text-accent hover:underline">Start over</button>
          </div>
        ) : (
          <>
            <div className="mb-6 text-center">
              <h2 className="text-lg font-semibold">Screening candidates</h2>
              <p className="mt-1 text-sm text-muted">
                {job ? `${job.processed}/${job.total} processed` : "Starting…"}
                {job && job.elapsed_seconds > 0 && <span className="text-faint"> · {job.elapsed_seconds}s</span>}
              </p>
            </div>

            <div className="mb-6 h-2 overflow-hidden rounded-full bg-line">
              <div className="h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${progress}%` }} />
            </div>

            <ol className="space-y-3">
              {STEPS.slice(0, 3).map((s, i) => {
                const done = activeIdx > i || current === "done";
                const active = activeIdx === i;
                return (
                  <li key={s.key} className="flex items-center gap-3">
                    <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs ${
                      done ? "bg-success text-white" : active ? "bg-accent text-white" : "bg-elevated text-faint"
                    }`}>
                      {done ? "✓" : i + 1}
                    </span>
                    <span className={`text-sm ${active ? "font-medium text-fg" : done ? "text-muted" : "text-faint"}`}>
                      {s.label}
                      {active && <span className="ml-1 inline-block animate-pulse">…</span>}
                    </span>
                  </li>
                );
              })}
            </ol>
          </>
        )}
      </div>
    </div>
  );
}
