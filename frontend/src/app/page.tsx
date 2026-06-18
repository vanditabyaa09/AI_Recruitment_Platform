"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, FileSearch, Brain, Shield, Sparkles, BarChart3, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatCard } from "@/components/dashboard/stat-card";
import { Users, Gem, AlertTriangle, FileText } from "lucide-react";

const features = [
  {
    icon: FileSearch,
    title: "Semantic CV Matching",
    description: "Vector-based similarity scoring — no keyword matching. Rank candidates by true fit.",
  },
  {
    icon: Brain,
    title: "AI Explainability",
    description: "Understand strengths, gaps, risks, and growth potential for every candidate.",
  },
  {
    icon: Shield,
    title: "Bias & Diversity Analysis",
    description: "Surface educational and employer concentration without inferring protected attributes.",
  },
  {
    icon: MessageSquare,
    title: "Recruiter Copilot",
    description: "Ask questions about your candidate pool with RAG-powered chat.",
  },
];

export default function HomePage() {
  return (
    <div className="min-h-screen">
      {/* Hero */}
      <section className="relative overflow-hidden px-6 py-24">
        <div className="absolute inset-0 -z-10">
          <div className="absolute left-1/4 top-0 h-96 w-96 rounded-full bg-blue-200/30 blur-3xl" />
          <div className="absolute right-1/4 bottom-0 h-96 w-96 rounded-full bg-teal-200/30 blur-3xl" />
        </div>

        <div className="mx-auto max-w-4xl text-center">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
            <span className="mb-4 inline-flex items-center gap-2 rounded-full bg-blue-50 px-4 py-1.5 text-sm font-medium text-blue-600">
              <Sparkles className="h-4 w-4" />
              AI-Augmented Recruitment
            </span>
            <h1 className="mt-6 text-5xl font-bold tracking-tight text-slate-900 md:text-6xl">
              Screen 1,000 CVs.{" "}
              <span className="gradient-text">Surface the 10 who matter.</span>
            </h1>
            <p className="mx-auto mt-6 max-w-2xl text-lg text-slate-600">
              RecruitIQ AI semantically evaluates candidates, ranks them, explains rankings,
              flags diversity concerns, and generates tailored interview questions.
            </p>
            <div className="mt-10 flex items-center justify-center gap-4">
              <Link href="/dashboard">
                <Button size="lg" className="gap-2">
                  Launch Dashboard <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
              <Link href="/analytics">
                <Button variant="outline" size="lg">
                  View Analytics
                </Button>
              </Link>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Stats */}
      <section className="mx-auto max-w-7xl px-6 pb-16">
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard title="Total CVs Processed" value="1,000+" icon={FileText} color="bg-blue-600" delay={0.1} />
          <StatCard title="Candidates Ranked" value="950+" icon={Users} color="bg-slate-900" delay={0.2} />
          <StatCard title="Hidden Gems Found" value="47" icon={Gem} color="bg-teal-500" delay={0.3} />
          <StatCard title="Diversity Alerts" value="12" icon={AlertTriangle} color="bg-amber-500" delay={0.4} />
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-7xl px-6 py-16">
        <h2 className="mb-12 text-center text-3xl font-bold text-slate-900">Platform Capabilities</h2>
        <div className="grid gap-8 md:grid-cols-2">
          {features.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.1 }}
              viewport={{ once: true }}
              className="glass rounded-2xl p-8"
            >
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-blue-100">
                <f.icon className="h-6 w-6 text-blue-600" />
              </div>
              <h3 className="text-xl font-semibold text-slate-900">{f.title}</h3>
              <p className="mt-2 text-slate-600">{f.description}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-7xl px-6 py-16">
        <div className="glass rounded-2xl p-12 text-center">
          <BarChart3 className="mx-auto h-12 w-12 text-blue-600" />
          <h2 className="mt-4 text-3xl font-bold text-slate-900">Ready to transform your hiring?</h2>
          <p className="mx-auto mt-4 max-w-lg text-slate-600">
            Upload a job description and batch of CVs to get AI-powered rankings in minutes.
          </p>
          <Link href="/dashboard" className="mt-8 inline-block">
            <Button size="lg">Start Screening</Button>
          </Link>
        </div>
      </section>
    </div>
  );
}
