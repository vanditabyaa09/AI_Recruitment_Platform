"use client";

import { useState, useCallback, useEffect } from "react";
import { motion } from "framer-motion";
import { Upload, FileText, Users, Play, Sparkles, Briefcase } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { StatCard } from "@/components/dashboard/stat-card";
import { ProcessingStatus } from "@/components/dashboard/processing-status";
import { DiversityAlertsPanel } from "@/components/dashboard/diversity-alerts";
import { ParsedJDPreview } from "@/components/dashboard/parsed-jd-preview";
import { useApp } from "@/context/app-context";
import { api, CandidateListItem, Analytics, JobDescription } from "@/lib/api";
import { getScoreColor, formatScore } from "@/lib/utils";
import Link from "next/link";
import { Gem, AlertTriangle, FileText as FileIcon } from "lucide-react";

export default function DashboardPage() {
  const { activeJDId, setActiveJDId, jobDescriptions, refreshJDs, backendConnected } = useApp();
  const [jdText, setJdText] = useState("");
  const [jdFile, setJdFile] = useState<File | null>(null);
  const [cvFiles, setCvFiles] = useState<File[]>([]);
  const [cvInputKey, setCvInputKey] = useState(0);
  const [processingJobId, setProcessingJobId] = useState<string | null>(null);
  const [rankingJobId, setRankingJobId] = useState<string | null>(null);
  const [loading, setLoading] = useState("");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<CandidateListItem[]>([]);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [activeJD, setActiveJD] = useState<JobDescription | null>(null);
  const [recommendation, setRecommendation] = useState<Record<string, unknown> | null>(null);

  const refreshData = useCallback(async () => {
    if (!activeJDId) return;
    try {
      const [candRes, analyticsRes, jdRes] = await Promise.all([
        api.listCandidates({ job_description_id: activeJDId, page_size: 10 }),
        api.getAnalytics(activeJDId),
        api.getJobDescription(activeJDId),
      ]);
      setCandidates(candRes.items);
      setAnalytics(analyticsRes);
      setActiveJD(jdRes);
    } catch {
      /* ignore */
    }
  }, [activeJDId]);

  useEffect(() => {
    if (activeJDId) refreshData();
  }, [activeJDId, refreshData]);

  const handleUploadJD = async () => {
    setLoading("jd");
    try {
      const jd = await api.uploadJD(jdFile || undefined, jdText || undefined);
      setActiveJDId(jd.id);
      await refreshJDs();
      setJdText("");
      setJdFile(null);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to upload JD");
    }
    setLoading("");
  };

  const handleUploadCVs = async () => {
    if (!activeJDId) {
      setUploadError("Upload a job description first, or select one from the dropdown above.");
      return;
    }
    if (cvFiles.length === 0) {
      setUploadError("Select one or more resume files (PDF, DOCX, or TXT).");
      return;
    }
    setLoading("cvs");
    setUploadError(null);
    setUploadSuccess(null);
    try {
      const res = await api.uploadCVs(activeJDId, cvFiles);
      setProcessingJobId(res.job_id);
      setUploadSuccess(`Upload started — processing ${res.total} resume(s).`);
      setCvFiles([]);
      setCvInputKey((k) => k + 1);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "Failed to upload CVs");
    }
    setLoading("");
  };

  const handleRank = async () => {
    if (!activeJDId) return;
    setLoading("rank");
    try {
      const res = await api.rankCandidates(activeJDId);
      setRankingJobId(res.job_id);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to start ranking");
    }
    setLoading("");
  };

  const handleRecommendation = async () => {
    if (!activeJDId) return;
    try {
      const rec = await api.hiringRecommendation(activeJDId);
      setRecommendation(rec);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <h1 className="text-3xl font-bold text-slate-900">Recruiter Dashboard</h1>
        <p className="mt-1 text-slate-600">Upload, process, and rank candidates with AI</p>
        {!backendConnected && (
          <p className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
            Cannot reach the backend at {process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}.
            Make sure the backend server is running.
          </p>
        )}
      </motion.div>

      {/* Stats */}
      <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard title="Total CVs" value={analytics?.total_cvs ?? 0} icon={FileIcon} color="bg-blue-600" />
        <StatCard title="Ranked" value={analytics?.candidates_ranked ?? 0} icon={Users} color="bg-slate-900" />
        <StatCard title="Hidden Gems" value={analytics?.hidden_gems ?? 0} icon={Gem} color="bg-teal-500" />
        <StatCard title="Diversity Alerts" value={analytics?.diversity_alerts ?? 0} icon={AlertTriangle} color="bg-amber-500" />
      </div>

      {/* JD Selector */}
      {jobDescriptions.length > 0 && (
        <Card className="mt-8">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Briefcase className="h-4 w-4" /> Active Job Description
            </CardTitle>
          </CardHeader>
          <CardContent>
            <select
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
              value={activeJDId || ""}
              onChange={(e) => setActiveJDId(e.target.value)}
            >
              {jobDescriptions.map((jd) => (
                <option key={jd.id} value={jd.id}>{jd.title}</option>
              ))}
            </select>
          </CardContent>
        </Card>
      )}

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        {/* JD Upload */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-blue-600" /> Job Description
            </CardTitle>
            <CardDescription>Upload PDF, DOCX, TXT or paste text</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Input type="file" accept=".pdf,.docx,.txt" onChange={(e) => setJdFile(e.target.files?.[0] || null)} />
            <textarea
              className="w-full rounded-lg border border-slate-200 p-3 text-sm"
              rows={4}
              placeholder="Or paste job description text..."
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
            />
            <Button onClick={handleUploadJD} disabled={loading === "jd" || (!jdFile && !jdText)}>
              {loading === "jd" ? "Uploading..." : "Upload JD"}
            </Button>
          </CardContent>
        </Card>

        {/* CV Upload */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Upload className="h-5 w-5 text-teal-500" /> CV Batch Upload
            </CardTitle>
            <CardDescription>Upload 20+ CVs (PDF, DOCX, TXT)</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Input
              key={cvInputKey}
              type="file"
              accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
              multiple
              onChange={(e) => {
                setCvFiles(Array.from(e.target.files || []));
                setUploadError(null);
              }}
            />
            {cvFiles.length > 0 && (
              <Badge variant="secondary">{cvFiles.length} files selected</Badge>
            )}
            {!activeJDId && (
              <p className="text-sm text-amber-700">
                Step 1: Upload or select a job description before uploading resumes.
              </p>
            )}
            {uploadError && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{uploadError}</p>
            )}
            {uploadSuccess && (
              <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{uploadSuccess}</p>
            )}
            <Button onClick={handleUploadCVs} disabled={!activeJDId || cvFiles.length === 0 || loading === "cvs"}>
              {loading === "cvs" ? "Uploading..." : cvFiles.length > 0 ? `Upload ${cvFiles.length} CVs` : "Upload CVs"}
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Processing & Actions */}
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <ProcessingStatus jobId={processingJobId} onComplete={refreshData} />
        <ProcessingStatus jobId={rankingJobId} onComplete={refreshData} />

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Actions</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-3">
            <Button onClick={handleRank} disabled={!activeJDId || loading === "rank"}>
              <Play className="h-4 w-4" /> Rank Candidates
            </Button>
            <Button variant="accent" onClick={handleRecommendation} disabled={!activeJDId}>
              <Sparkles className="h-4 w-4" /> Hiring Recommendation
            </Button>
            <Button variant="outline" onClick={refreshData} disabled={!activeJDId}>
              Refresh Results
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Parsed JD & Diversity */}
      {activeJD && (
        <div className="mt-8 grid gap-6 lg:grid-cols-2">
          <ParsedJDPreview jd={activeJD} />
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Bias & Diversity Flags</CardTitle>
              <CardDescription>Homogeneous shortlist detection and hidden gems</CardDescription>
            </CardHeader>
            <CardContent>
              <DiversityAlertsPanel
                alerts={analytics?.diversity_alert_list || []}
                insights={analytics?.diversity_insights}
              />
            </CardContent>
          </Card>
        </div>
      )}

      {/* Recommendation */}
      {recommendation && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>AI Hiring Recommendation</CardTitle>
            <CardDescription>{String(recommendation.summary)}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <h4 className="font-medium text-slate-900">Primary Recommendations</h4>
                <ul className="mt-2 space-y-2">
                  {(recommendation.primary_recommendations as { name: string; score: number; rationale: string }[])?.map((r, i) => (
                    <li key={i} className="rounded-lg bg-blue-50 p-3 text-sm">
                      <strong>{r.name}</strong> — {formatScore(r.score)}% — {r.rationale}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h4 className="font-medium text-slate-900">Next Steps</h4>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">
                  {(recommendation.next_steps as string[])?.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Top Rankings */}
      <Card className="mt-8">
        <CardHeader>
          <CardTitle>Top Ranked Candidates</CardTitle>
          <CardDescription>
            <Link href="/candidates" className="text-blue-600 hover:underline">View all candidates →</Link>
          </CardDescription>
        </CardHeader>
        <CardContent>
          {candidates.length === 0 ? (
            <p className="text-sm text-slate-500">Upload CVs and run ranking to see results.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-slate-500">
                    <th className="pb-3 pr-4">Rank</th>
                    <th className="pb-3 pr-4">Name</th>
                    <th className="pb-3 pr-4">Score</th>
                    <th className="pb-3 pr-4">Experience</th>
                    <th className="pb-3">Skills</th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((c) => (
                    <tr key={c.id} className="border-b border-slate-100">
                      <td className="py-3 pr-4 font-medium">#{c.rank ?? "-"}</td>
                      <td className="py-3 pr-4">
                        <Link href={`/candidates/${c.id}`} className="text-blue-600 hover:underline">
                          {c.name}
                        </Link>
                        {c.is_hidden_gem && <Badge variant="gem" className="ml-2">Gem</Badge>}
                      </td>
                      <td className={`py-3 pr-4 font-semibold ${getScoreColor(c.overall_score)}`}>
                        {formatScore(c.overall_score)}
                      </td>
                      <td className="py-3 pr-4">{c.years_of_experience}y</td>
                      <td className="py-3">{c.top_skills.slice(0, 3).join(", ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
