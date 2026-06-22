"use client";

import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { GitCompare, Gem } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { useApp } from "@/context/app-context";
import { useToast } from "@/context/toast-context";
import { api, CandidateListItem, ComparedCandidate } from "@/lib/api";
import { formatScore, getScoreColor } from "@/lib/utils";
import Link from "next/link";

export default function ComparePage() {
  const { activeJDId } = useApp();
  const { addToast } = useToast();
  const [candidates, setCandidates] = useState<CandidateListItem[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [comparison, setComparison] = useState<ComparedCandidate[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!activeJDId) return;
    api.listCandidates({ job_description_id: activeJDId, page_size: 50, sort_by: "score", sort_order: "desc" })
      .then((res) => setCandidates(res.items))
      .catch(() => addToast("Failed to load candidates.", "error"));
  }, [activeJDId, addToast]);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 4) return prev;
      return [...prev, id];
    });
  };

  const handleCompare = async () => {
    if (selected.length < 2) return;
    setLoading(true);
    try {
      const res = await api.compareCandidates(selected, activeJDId || undefined);
      setComparison(res.candidates);
    } catch {
      addToast("Comparison failed. Please try again.", "error");
    }
    setLoading(false);
  };

  const chartData = comparison.map((c) => ({
    name: c.name.split(" ")[0],
    Overall: c.scores?.overall ?? 0,
    Skills: c.scores?.skill ?? 0,
    Experience: c.scores?.experience ?? 0,
  }));

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <h1 className="text-3xl font-bold text-slate-900">Candidate Comparison</h1>
      <p className="mt-1 text-slate-600">Select 2–4 candidates to compare side-by-side</p>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <GitCompare className="h-5 w-5 text-blue-600" /> Select Candidates
          </CardTitle>
          <CardDescription>Choose from your ranked pool ({selected.length}/4 selected)</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {candidates.map((c) => (
              <button
                key={c.id}
                onClick={() => toggleSelect(c.id)}
                className={`rounded-lg border px-3 py-2 text-sm transition-colors ${
                  selected.includes(c.id)
                    ? "border-blue-600 bg-blue-50 text-blue-700"
                    : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                }`}
              >
                #{c.rank ?? "-"} {c.name}
                {c.is_hidden_gem && <Gem className="ml-1 inline h-3 w-3 text-purple-500" />}
              </button>
            ))}
          </div>
          <Button className="mt-4" onClick={handleCompare} disabled={selected.length < 2 || loading}>
            {loading ? "Comparing..." : "Compare Selected"}
          </Button>
        </CardContent>
      </Card>

      {comparison.length >= 2 && (
        <>
          <div className="mt-8 grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader><CardTitle>Score Comparison</CardTitle></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="Overall" fill="#2563EB" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="Skills" fill="#14B8A6" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="Experience" fill="#0F172A" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>Side-by-Side</CardTitle></CardHeader>
              <CardContent>
                <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${comparison.length}, 1fr)` }}>
                  {comparison.map((c) => (
                    <div key={c.id} className="rounded-lg border border-slate-100 p-4">
                      <Link href={`/candidates/${c.id}`} className="font-semibold text-blue-600 hover:underline">
                        {c.name}
                      </Link>
                      {c.is_hidden_gem && <Badge variant="gem" className="ml-2">Gem</Badge>}
                      <p className={`mt-2 text-2xl font-bold ${getScoreColor(c.scores?.overall ?? 0)}`}>
                        {formatScore(c.scores?.overall ?? 0)}%
                      </p>
                      <p className="text-xs text-slate-500">Rank #{c.rank ?? "-"} • {c.years_of_experience}y exp</p>
                      <div className="mt-3 flex flex-wrap gap-1">
                        {c.skills.slice(0, 6).map((s) => (
                          <Badge key={s} variant="secondary">{s}</Badge>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
