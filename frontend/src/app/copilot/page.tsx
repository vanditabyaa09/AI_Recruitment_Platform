"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Bot, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { useApp } from "@/context/app-context";
import { api } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
}

const SUGGESTIONS = [
  "Why was the top candidate ranked highest?",
  "Show strongest Python candidates",
  "Show candidates lacking AWS",
  "Find hidden gems",
  "Generate hiring recommendation",
];

export default function CopilotPage() {
  const { activeJDId } = useApp();
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", content: "Hi! I'm your RecruitIQ Copilot. Ask me anything about your candidate pool." },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const sessionId = useRef(`session-${Date.now()}`);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async (text: string) => {
    if (!text.trim()) return;
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setLoading(true);

    try {
      const res = await api.chat(text, sessionId.current, activeJDId || undefined);
      setMessages((prev) => [...prev, { role: "assistant", content: res.response }]);
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "Sorry, I couldn't process that request. Make sure the backend is running." }]);
    }
    setLoading(false);
  };

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <h1 className="text-3xl font-bold text-slate-900">Recruiter Copilot</h1>
      <p className="mt-1 text-slate-600">AI-powered chat over your candidate data</p>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bot className="h-5 w-5 text-blue-600" /> Chat
          </CardTitle>
          <CardDescription>RAG-powered assistant for recruitment decisions</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="mb-4 flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => sendMessage(s)}
                className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600 transition-colors hover:bg-blue-50 hover:text-blue-600"
              >
                {s}
              </button>
            ))}
          </div>

          <div className="h-[400px] overflow-y-auto rounded-lg border border-slate-100 p-4">
            {messages.map((msg, i) => (
              <div key={i} className={`mb-4 flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}>
                {msg.role === "assistant" && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100">
                    <Bot className="h-4 w-4 text-blue-600" />
                  </div>
                )}
                <div
                  className={`max-w-[80%] rounded-lg px-4 py-2 text-sm ${
                    msg.role === "user"
                      ? "bg-blue-600 text-white"
                      : "bg-slate-50 text-slate-700"
                  }`}
                >
                  {msg.content}
                </div>
                {msg.role === "user" && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-200">
                    <User className="h-4 w-4 text-slate-600" />
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div className="flex gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-100">
                  <Bot className="h-4 w-4 animate-pulse text-blue-600" />
                </div>
                <div className="rounded-lg bg-slate-50 px-4 py-2 text-sm text-slate-400">Thinking...</div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <form
            className="mt-4 flex gap-2"
            onSubmit={(e) => { e.preventDefault(); sendMessage(input); }}
          >
            <Input
              placeholder="Ask about candidates..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={loading}
            />
            <Button type="submit" disabled={loading || !input.trim()}>
              <Send className="h-4 w-4" />
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
