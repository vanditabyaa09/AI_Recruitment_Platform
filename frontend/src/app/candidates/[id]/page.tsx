"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer,
} from "recharts";
import { Download, Sparkles, ArrowLeft, Gem } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, CandidateDetail } from "@/lib/api";
import { useToast } from "@/context/toast-context";
import { formatScore, getScoreColor } from "@/lib/utils";

export default function CandidateProfilePage() {
  const params = useParams();
  const id = params.id as string;
  const [candidate, setCandidate] = useState<CandidateDetail | null>(null);
  const [loadingQuestions, setLoadingQuestions] = useState(false);
  const { addToast } = useToast();

  useEffect(() => {
    api.getCandidate(id).then(setCandidate).catch(() => addToast("Failed to load candidate profile.", "error"));
  }, [id, addToast]);

  const handleGenerateQuestions = async () => {
    setLoadingQuestions(true);
    try {
      await api.generateQuestions(id);
      const updated = await api.getCandidate(id);
      setCandidate(updated);
    } catch {
      addToast("Failed to generate interview questions.", "error");
    }
    setLoadingQuestions(false);
  };

  const handleDownloadReport = async () => {
    try {
      const blob = await api.downloadReport(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${candidate?.name || "candidate"}_report.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      addToast("Failed to download report.", "error");
    }
  };

  if (!candidate) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <p className="text-slate-500">Loading candidate profile...</p>
      </div>
    );
  }

  const radarData = candidate.scores
    ? [
        { subject: "Skills", value: candidate.scores.skill_score },
        { subject: "Experience", value: candidate.scores.experience_score },
        { subject: "Domain", value: candidate.scores.domain_score },
        { subject: "Education", value: candidate.scores.education_score },
        { subject: "Soft Skills", value: candidate.scores.soft_skill_score },
      ]
    : [];

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <Link href="/candidates" className="mb-4 inline-flex items-center gap-1 text-sm text-blue-600 hover:underline">
        <ArrowLeft className="h-4 w-4" /> Back to candidates
      </Link>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-bold text-slate-900">{candidate.name}</h1>
              {candidate.is_hidden_gem && <Badge variant="gem"><Gem className="mr-1 h-3 w-3" /> Hidden Gem</Badge>}
              {candidate.rank && <Badge variant="default">Rank #{candidate.rank}</Badge>}
            </div>
            <p className="mt-1 text-slate-600">
              {candidate.email} {candidate.location && `• ${candidate.location}`}
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={handleDownloadReport}>
              <Download className="h-4 w-4" /> Download Report
            </Button>
            <Button onClick={handleGenerateQuestions} disabled={loadingQuestions}>
              <Sparkles className="h-4 w-4" />
              {loadingQuestions ? "Generating..." : "Generate Questions"}
            </Button>
          </div>
        </div>
      </motion.div>

      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        {/* Scores & Radar */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>AI Fit Analysis</CardTitle>
          </CardHeader>
          <CardContent>
            {candidate.scores && (
              <>
                <p className={`text-4xl font-bold ${getScoreColor(candidate.scores.overall_score)}`}>
                  {formatScore(candidate.scores.overall_score)}%
                </p>
                <p className="text-sm text-slate-500">Overall Match Score</p>
                <div className="mt-6 h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart data={radarData}>
                      <PolarGrid />
                      <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11 }} />
                      <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fontSize: 10 }} />
                      <Radar dataKey="value" stroke="#2563EB" fill="#2563EB" fillOpacity={0.3} />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Explanation */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Fit Explanation</CardTitle>
          </CardHeader>
          <CardContent>
            {candidate.executive_summary && (
              <p className="mb-6 rounded-lg bg-blue-50 p-4 text-sm text-slate-700">{candidate.executive_summary}</p>
            )}
            <div className="grid gap-6 md:grid-cols-2">
              {[
                { title: "Strengths", items: candidate.explanation?.strengths, color: "text-emerald-600" },
                { title: "Gaps", items: candidate.explanation?.gaps, color: "text-amber-600" },
                { title: "Risks", items: candidate.explanation?.risks, color: "text-red-600" },
                { title: "Potential", items: candidate.explanation?.potential, color: "text-teal-600" },
              ].map(({ title, items, color }) => (
                <div key={title}>
                  <h4 className={`font-semibold ${color}`}>{title}</h4>
                  <ul className="mt-2 space-y-1 text-sm text-slate-600">
                    {items?.map((item, i) => <li key={i}>• {item}</li>) || <li>—</li>}
                  </ul>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Skills, Education & Experience */}
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader><CardTitle>Skills</CardTitle></CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {candidate.skills.map((s) => <Badge key={s} variant="secondary">{s}</Badge>)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Education</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-3">
              {((candidate.parsed_data?.education as { institution?: string; degree?: string; year?: string }[]) || []).length > 0 ? (
                (candidate.parsed_data.education as { institution?: string; degree?: string; year?: string }[]).map((edu, i) => (
                  <div key={i}>
                    <p className="font-medium text-slate-900">{edu.degree || "Degree"}</p>
                    <p className="text-sm text-slate-600">{edu.institution}</p>
                    {edu.year && <p className="text-xs text-slate-400">{edu.year}</p>}
                  </div>
                ))
              ) : (
                <p className="text-sm text-slate-500">No education data extracted.</p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Projects</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-3">
              {((candidate.parsed_data?.projects as { name?: string; description?: string }[]) || []).length > 0 ? (
                (candidate.parsed_data.projects as { name?: string; description?: string }[]).map((proj, i) => (
                  <div key={i} className="rounded-lg bg-slate-50 p-3">
                    <p className="font-medium text-slate-900">{proj.name}</p>
                    {proj.description && <p className="mt-1 text-sm text-slate-600">{proj.description}</p>}
                  </div>
                ))
              ) : (
                <p className="text-sm text-slate-500">No projects listed.</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader><CardTitle>Experience Timeline</CardTitle></CardHeader>
        <CardContent>
          <div className="space-y-4">
            {candidate.experiences.map((exp, i) => (
              <div key={i} className="border-l-2 border-blue-200 pl-4">
                <p className="font-medium text-slate-900">{exp.role}</p>
                <p className="text-sm text-slate-600">{exp.company}</p>
                <p className="text-xs text-slate-400">{exp.start} — {exp.end || "Present"}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Interview Questions */}
      <Card className="mt-6">
        <CardHeader><CardTitle>Interview Questions</CardTitle></CardHeader>
        <CardContent>
          {candidate.interview_questions.length === 0 ? (
            <p className="text-sm text-slate-500">Click &quot;Generate Questions&quot; to create personalized interview questions.</p>
          ) : (
            <div className="space-y-4">
              {candidate.interview_questions.map((q, i) => (
                <div key={i} className="rounded-lg border border-slate-100 p-4">
                  <Badge variant="outline" className="mb-2">{q.category}</Badge>
                  <p className="text-sm text-slate-700">{q.question}</p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
