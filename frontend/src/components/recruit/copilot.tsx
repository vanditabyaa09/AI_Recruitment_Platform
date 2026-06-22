"use client";

import { useState, useRef, useEffect } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

interface Msg {
  role: "user" | "assistant";
  text: string;
}

const SUGGESTIONS = [
  "Who are the top 3 candidates and why?",
  "Which candidates lack AWS experience?",
  "Surface any hidden gems worth a closer look.",
  "Who should we interview first?",
];

export function Copilot({ jobId, onClose }: { jobId: string; onClose: () => void }) {
  const [messages, setMessages] = useState<Msg[]>([
    { role: "assistant", text: "Ask me anything about this candidate pool — comparisons, gaps, hidden gems, or hiring recommendations." },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);

  const send = async (text: string) => {
    if (!text.trim() || busy) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setBusy(true);
    try {
      const { response } = await api.chat(jobId, text);
      setMessages((m) => [...m, { role: "assistant", text: response }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", text: e instanceof Error ? e.message : "Something went wrong." }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative flex h-full w-full max-w-md flex-col border-l border-line bg-bg shadow-2xl animate-fade-up">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-soft text-accent">✦</span>
            <h3 className="font-semibold">Recruiter Copilot</h3>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-faint hover:bg-elevated hover:text-fg">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12" strokeLinecap="round" /></svg>
          </button>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-5">
          {messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              <div className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3.5 py-2 text-sm leading-relaxed ${
                m.role === "user" ? "bg-accent text-accent-fg" : "border border-line bg-card text-fg/90"
              }`}>
                {m.text}
              </div>
            </div>
          ))}
          {busy && <div className="flex justify-start"><div className="rounded-2xl border border-line bg-card px-3.5 py-2 text-sm text-muted">Thinking…</div></div>}
          <div ref={endRef} />
        </div>

        {messages.length <= 1 && (
          <div className="flex flex-wrap gap-2 px-5 pb-3">
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => send(s)} className="rounded-full border border-line px-3 py-1 text-xs text-muted transition-colors hover:border-accent hover:text-accent">
                {s}
              </button>
            ))}
          </div>
        )}

        <div className="border-t border-line p-4">
          <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about the candidates…"
              className="flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm focus:border-accent focus:outline-none"
            />
            <Button type="submit" disabled={!input.trim() || busy} size="icon">→</Button>
          </form>
        </div>
      </div>
    </div>
  );
}
