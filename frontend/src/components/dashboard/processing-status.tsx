"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { api, ProcessingJob } from "@/lib/api";
import { Loader2, CheckCircle2, XCircle } from "lucide-react";

interface ProcessingStatusProps {
  jobId: string | null;
  onComplete?: () => void;
}

export function ProcessingStatus({ jobId, onComplete }: ProcessingStatusProps) {
  const [job, setJob] = useState<ProcessingJob | null>(null);

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      return;
    }

    setJob({
      id: jobId,
      job_type: "processing",
      status: "pending",
      progress: 0,
      total_items: 0,
      message: "Starting...",
    });

    const poll = async () => {
      try {
        const status = await api.getProcessingStatus(jobId);
        setJob(status);
        if (status.status === "completed" || status.status === "failed") {
          onComplete?.();
          return true;
        }
      } catch {
        setJob((prev) =>
          prev
            ? { ...prev, status: "failed", message: "Could not reach the server. Is the backend running?" }
            : null
        );
        return true;
      }
      return false;
    };

    poll();
    const interval = setInterval(async () => {
      const done = await poll();
      if (done) clearInterval(interval);
    }, 1500);

    return () => clearInterval(interval);
  }, [jobId, onComplete]);

  if (!jobId || !job) return null;

  const pct = job.total_items > 0 ? (job.progress / job.total_items) * 100 : job.status === "pending" ? 5 : 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          {(job.status === "processing" || job.status === "pending") && (
            <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
          )}
          {job.status === "completed" && <CheckCircle2 className="h-4 w-4 text-emerald-500" />}
          {job.status === "failed" && <XCircle className="h-4 w-4 text-red-500" />}
          Processing Status
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-3 text-sm text-slate-600">{job.message || job.job_type}</p>
        <Progress value={pct} className="mb-2" />
        <p className="text-xs text-slate-400">
          {job.total_items > 0
            ? `${job.progress} / ${job.total_items} — ${job.status}`
            : job.status}
        </p>
      </CardContent>
    </Card>
  );
}
