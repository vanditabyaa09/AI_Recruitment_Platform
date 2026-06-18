"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Brain, LayoutDashboard, BarChart3, Users, MessageSquare, Sparkles, GitCompare } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/candidates", label: "Candidates", icon: Users },
  { href: "/compare", label: "Compare", icon: GitCompare },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/copilot", label: "Copilot", icon: MessageSquare },
];

export function Navbar() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-50 border-b border-white/20 bg-white/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-white">
            <Brain className="h-5 w-5" />
          </div>
          <div>
            <span className="text-lg font-bold text-slate-900">RecruitIQ</span>
            <span className="ml-1 text-lg font-light text-teal-500">AI</span>
          </div>
        </Link>

        <nav className="hidden items-center gap-1 md:flex">
          {navItems.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                pathname.startsWith(href)
                  ? "bg-blue-50 text-blue-600"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          ))}
        </nav>

        <Link
          href="/dashboard"
          className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
        >
          <Sparkles className="h-4 w-4" />
          Get Started
        </Link>
      </div>
    </header>
  );
}
