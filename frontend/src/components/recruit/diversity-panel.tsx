"use client";

import { DiversityReport } from "@/lib/api";
import { GemBadge } from "./ui-bits";

export function DiversityPanel({
  diversity,
  onSelect,
}: {
  diversity: DiversityReport;
  onSelect: (id: string) => void;
}) {
  const dist = diversity.distribution || {};
  return (
    <div className="surface p-5">
      <div className="mb-4 flex items-center gap-2">
        <span
          className={`inline-block h-2 w-2 rounded-full ${diversity.skewed ? "bg-warn" : "bg-success"}`}
        />
        <h3 className="text-sm font-semibold">Bias & Diversity</h3>
        <span className="ml-auto text-xs text-faint">
          {diversity.skewed ? "Skew detected" : "Looks balanced"}
        </span>
      </div>

      {/* flags */}
      <div className="space-y-2">
        {diversity.flags.map((f, i) => (
          <div
            key={i}
            className={`rounded-lg border p-3 ${
              f.severity === "warning"
                ? "border-warn/30 bg-warn-soft"
                : "border-line bg-surface/60"
            }`}
          >
            <div className="flex items-center gap-2">
              <span className={f.severity === "warning" ? "text-warn" : "text-info"}>
                {f.severity === "warning" ? "⚠" : "ℹ"}
              </span>
              <span className="text-sm font-medium">{f.title}</span>
            </div>
            <p className="mt-1 pl-6 text-xs leading-relaxed text-muted">{f.detail}</p>
          </div>
        ))}
      </div>

      {/* hidden gems */}
      {diversity.hidden_gems.length > 0 && (
        <div className="mt-4">
          <div className="mb-2 flex items-center gap-2">
            <GemBadge />
            <span className="text-xs text-muted">scored well, non-traditional background</span>
          </div>
          <div className="space-y-1.5">
            {diversity.hidden_gems.map((g) => (
              <button
                key={g.id}
                onClick={() => onSelect(g.id)}
                className="flex w-full items-center justify-between rounded-lg border border-line bg-surface/60 px-3 py-2 text-left transition-colors hover:border-gem/40"
              >
                <span className="text-sm font-medium">{g.name}</span>
                <span className="num text-xs text-gem">{Math.round(g.overall)}%</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* distribution */}
      <div className="mt-4 space-y-3">
        <DistRow title="Score bands" data={dist.score_bands} order={["80-100", "65-80", "50-65", "<50"]} />
        <DistRow title="Experience" data={dist.experience} order={["0-2y", "2-5y", "5-8y", "8-12y", "12y+"]} />
        <DistRow title="Education" data={dist.education} order={["doctorate", "masters", "bachelors", "other", "none"]} />
      </div>
    </div>
  );
}

function DistRow({
  title,
  data,
  order,
}: {
  title: string;
  data?: Record<string, number>;
  order: string[];
}) {
  if (!data || Object.keys(data).length === 0) return null;
  const total = Object.values(data).reduce((a, b) => a + b, 0) || 1;
  const keys = order.filter((k) => data[k]);
  return (
    <div>
      <span className="label">{title}</span>
      <div className="mt-1.5 flex h-2 overflow-hidden rounded-full bg-line">
        {keys.map((k, i) => (
          <div
            key={k}
            title={`${k}: ${data[k]}`}
            style={{
              width: `${(data[k] / total) * 100}%`,
              background: `hsl(${220 - i * 35} 55% 58%)`,
            }}
          />
        ))}
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-faint">
        {keys.map((k) => (
          <span key={k}>{k} · {data[k]}</span>
        ))}
      </div>
    </div>
  );
}
