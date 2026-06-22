"use client";

import { useMemo, useState } from "react";
import { api, ResultsResponse, CandidateSummary } from "@/lib/api";
import { ScoreRing, RecommendationBadge, GemBadge, SkillChip } from "./ui-bits";
import { DiversityPanel } from "./diversity-panel";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface Props {
  results: ResultsResponse;
  onSelect: (id: string) => void;
  onCopilot: () => void;
  onReset: () => void;
}

type Filter = "all" | "shortlist" | "gems";

export function Results({ results, onSelect, onCopilot, onReset }: Props) {
  const { candidates, diversity, jd } = results;
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const shortlistSize = diversity.shortlist_size || 10;
  const avg = candidates.length
    ? candidates.reduce((a, c) => a + c.overall, 0) / candidates.length
    : 0;

  const filtered = useMemo(() => {
    let list = candidates;
    if (filter === "shortlist") list = list.filter((c) => c.rank <= shortlistSize);
    if (filter === "gems") list = list.filter((c) => c.is_hidden_gem);
    const q = query.trim().toLowerCase();
    if (q)
      list = list.filter(
        (c) =>
          c.name.toLowerCase().includes(q) ||
          c.top_skills.some((s) => s.toLowerCase().includes(q)),
      );
    return list;
  }, [candidates, filter, query, shortlistSize]);

  return (
    <div className="space-y-6">
      {/* header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{jd.parsed.role || jd.title}</h1>
          <p className="text-sm text-muted">
            {jd.parsed.seniority} · {jd.parsed.experience_required} · screened{" "}
            <span className="num text-fg">{candidates.length}</span> candidates in{" "}
            <span className="num text-fg">{results.elapsed_seconds}s</span>
            {!results.using_ai && <span className="text-warn"> · offline mode</span>}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="accent" size="sm" onClick={onCopilot}>✦ Copilot</Button>
          <a href={api.csvUrl(results.job_id)} target="_blank" rel="noreferrer">
            <Button variant="secondary" size="sm">Export CSV</Button>
          </a>
          <Button variant="ghost" size="sm" onClick={onReset}>New screening</Button>
        </div>
      </div>

      {/* stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Candidates" value={candidates.length} />
        <Stat label="Shortlisted" value={Math.min(shortlistSize, candidates.length)} accent />
        <Stat label="Hidden gems" value={diversity.hidden_gems.length} gem />
        <Stat label="Avg score" value={`${Math.round(avg)}%`} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* ranked list */}
        <div className="lg:col-span-2">
          {/* toolbar */}
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <div className="flex rounded-lg border border-line p-0.5">
              {(["all", "shortlist", "gems"] as Filter[]).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={cn(
                    "rounded-md px-3 py-1 text-xs font-medium capitalize transition-colors",
                    filter === f ? "bg-elevated text-fg" : "text-muted hover:text-fg",
                  )}
                >
                  {f === "gems" ? "Hidden gems" : f}
                </button>
              ))}
            </div>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search name or skill…"
              className="flex-1 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm focus:border-accent focus:outline-none"
            />
          </div>

          <div className="space-y-2">
            {filtered.map((c) => (
              <CandidateRow key={c.id} c={c} shortlist={c.rank <= shortlistSize} onClick={() => onSelect(c.id)} />
            ))}
            {filtered.length === 0 && (
              <p className="rounded-lg border border-line bg-surface/60 p-6 text-center text-sm text-faint">
                No candidates match.
              </p>
            )}
          </div>
        </div>

        {/* diversity */}
        <div className="lg:col-span-1">
          <DiversityPanel diversity={diversity} onSelect={onSelect} />
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, accent, gem }: { label: string; value: string | number; accent?: boolean; gem?: boolean }) {
  return (
    <div className="surface p-4">
      <span className="label">{label}</span>
      <p className={cn("num mt-1 text-2xl font-semibold", accent && "text-accent", gem && "text-gem")}>{value}</p>
    </div>
  );
}

function CandidateRow({ c, shortlist, onClick }: { c: CandidateSummary; shortlist: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "group flex w-full items-center gap-4 rounded-xl border bg-card p-4 text-left transition-all hover:border-line-strong hover:bg-elevated",
        shortlist ? "border-line" : "border-line/60 opacity-90",
      )}
    >
      <span className="num w-6 shrink-0 text-center text-sm font-semibold text-faint">{c.rank}</span>
      <ScoreRing score={c.overall} size={46} stroke={4} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate font-medium">{c.name}</span>
          {c.is_hidden_gem && <GemBadge />}
        </div>
        <p className="truncate text-xs text-muted">{c.summary || c.headline}</p>
        <div className="mt-1.5 flex flex-wrap gap-1">
          {c.top_skills.slice(0, 5).map((s) => <SkillChip key={s} skill={s} matched />)}
        </div>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1.5">
        <RecommendationBadge rec={c.recommendation} />
        <span className="text-xs text-faint">{c.years_of_experience}y</span>
      </div>
    </button>
  );
}
