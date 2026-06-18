"use client";

import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, FunnelChart, Funnel, LabelList,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DiversityAlertsPanel } from "@/components/dashboard/diversity-alerts";
import { useApp } from "@/context/app-context";
import { api, Analytics } from "@/lib/api";

const COLORS = ["#2563EB", "#14B8A6", "#0F172A", "#F59E0B", "#8B5CF6", "#EC4899"];

export default function AnalyticsPage() {
  const { activeJDId } = useApp();
  const [analytics, setAnalytics] = useState<Analytics | null>(null);

  useEffect(() => {
    api.getAnalytics(activeJDId || undefined).then(setAnalytics).catch(() => {});
  }, [activeJDId]);

  if (!analytics) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <p className="text-slate-500">Loading analytics...</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <h1 className="text-3xl font-bold text-slate-900">Analytics</h1>
      <p className="mt-1 text-slate-600">Insights from your candidate pipeline</p>

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        {/* Score Distribution */}
        <Card>
          <CardHeader><CardTitle>Candidate Score Distribution</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={analytics.score_distribution}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="range" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#2563EB" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Experience Distribution */}
        <Card>
          <CardHeader><CardTitle>Experience Distribution</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={analytics.experience_distribution}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="range" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#14B8A6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Skill Heatmap */}
        <Card>
          <CardHeader><CardTitle>Skill Heatmap</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={analytics.skill_heatmap.slice(0, 10)} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis type="number" tick={{ fontSize: 12 }} />
                <YAxis dataKey="skill" type="category" width={100} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#0F172A" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Education Breakdown */}
        <Card>
          <CardHeader><CardTitle>Education Breakdown</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={analytics.education_breakdown.slice(0, 6)}
                  dataKey="count"
                  nameKey="institution"
                  cx="50%"
                  cy="50%"
                  outerRadius={100}
                  label={({ name, percent }) => `${name} (${((percent ?? 0) * 100).toFixed(0)}%)`}
                >
                  {analytics.education_breakdown.slice(0, 6).map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Hiring Funnel */}
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>Hiring Funnel</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <FunnelChart>
                <Tooltip />
                <Funnel dataKey="count" data={analytics.hiring_funnel} isAnimationActive>
                  <LabelList position="right" fill="#64748b" stroke="none" dataKey="stage" />
                </Funnel>
              </FunnelChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Diversity Insights */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Bias & Diversity Flags</CardTitle>
          </CardHeader>
          <CardContent>
            <DiversityAlertsPanel
              alerts={analytics.diversity_alert_list || []}
              insights={analytics.diversity_insights}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
