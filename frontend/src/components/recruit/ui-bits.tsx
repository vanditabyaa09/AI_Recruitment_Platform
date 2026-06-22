"use client";

import { cn } from "@/lib/utils";

// ---- Recommendation badge ------------------------------------------------
const REC_MAP: Record<string, { label: string; cls: string }> = {
  strong_yes: { label: "Strong Yes", cls: "bg-success-soft text-success ring-success/30" },
  yes: { label: "Yes", cls: "bg-accent-soft text-accent ring-accent/30" },
  maybe: { label: "Maybe", cls: "bg-warn-soft text-warn ring-warn/30" },
  no: { label: "No", cls: "bg-danger-soft text-danger ring-danger/30" },
};

export function RecommendationBadge({ rec, className }: { rec: string; className?: string }) {
  const m = REC_MAP[rec] || { label: rec || "—", cls: "bg-elevated text-muted ring-line" };
  return (
    <span className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset", m.cls, className)}>
      {m.label}
    </span>
  );
}

// ---- Score color ---------------------------------------------------------
export function scoreColor(score: number): string {
  if (score >= 80) return "var(--color-success)";
  if (score >= 65) return "var(--color-accent)";
  if (score >= 50) return "var(--color-warn)";
  return "var(--color-danger)";
}

// ---- Circular score ring -------------------------------------------------
export function ScoreRing({ score, size = 56, stroke = 5 }: { score: number; size?: number; stroke?: number }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const offset = c - (Math.min(100, Math.max(0, score)) / 100) * c;
  const color = scoreColor(score);
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-line)" strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
          strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 0.8s cubic-bezier(0.4,0,0.2,1)" }}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="num font-semibold" style={{ color, fontSize: size * 0.28 }}>
          {Math.round(score)}
        </span>
      </div>
    </div>
  );
}

// ---- Horizontal score bar ------------------------------------------------
export function ScoreBar({ label, value }: { label: string; value: number }) {
  const color = scoreColor(value);
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-muted">{label}</span>
        <span className="num font-medium" style={{ color }}>{Math.round(value)}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-line">
        <div
          className="h-full rounded-full"
          style={{ width: `${Math.min(100, value)}%`, background: color, transition: "width 0.7s ease-out" }}
        />
      </div>
    </div>
  );
}

// ---- Skill chip ----------------------------------------------------------
export function SkillChip({ skill, matched }: { skill: string; matched?: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium",
        matched
          ? "bg-success-soft text-success ring-1 ring-inset ring-success/20"
          : "bg-elevated text-muted ring-1 ring-inset ring-line",
      )}
    >
      {skill}
    </span>
  );
}

// ---- Hidden gem badge ----------------------------------------------------
export function GemBadge({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full bg-gem-soft px-2 py-0.5 text-xs font-semibold text-gem ring-1 ring-inset ring-gem/30", className)}>
      <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3 6 7 .8-5 4.7 1.3 6.9L12 17.8 5.7 20.4 7 13.5 2 8.8 9 8z" /></svg>
      Hidden Gem
    </span>
  );
}
