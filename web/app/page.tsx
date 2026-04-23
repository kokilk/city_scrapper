"use client";

import { useState, useRef } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface DisplayPerson {
  rank?: number;
  full_name: string;
  title: string;
  company: string;
  phone: string;
  email: string;
  linkedin_url: string;
  confidence: string;
  property_address: string;
}

type StepStatus = "pending" | "running" | "done" | "error";

interface Step {
  label: string;
  detail: string;
  status: StepStatus;
}

type Phase = "idle" | "searching" | "done" | "error";

const INIT_STEPS: Step[] = [
  { label: "Building owner",        detail: "", status: "pending" },
  { label: "Company website",       detail: "", status: "pending" },
  { label: "Leadership data",       detail: "", status: "pending" },
  { label: "Contact enrichment",    detail: "", status: "pending" },
];

function parseLogToStep(msg: string, steps: Step[]): Step[] {
  const s = [...steps.map(s => ({ ...s }))];
  const m = msg.trim();

  if (m.includes("Step 1/4"))               { s[0].status = "running"; s[0].detail = ""; }
  if (m.includes("Owner:"))                 { s[0].status = "done";    s[0].detail = m.replace(/.*Owner:\s*/, "").trim(); }
  if (m.includes("Operating company:"))     { s[0].detail = m.replace(/.*Operating company:\s*/, "").trim(); }
  if (m.includes("Step 2/4"))               { s[1].status = "running"; s[1].detail = ""; }
  if (m.includes("Website:") && !m.includes("chars scraped")) {
    s[1].status = "done";
    const w = m.replace(/.*Website:\s*/, "").trim();
    s[1].detail = w.startsWith("http") ? new URL(w).hostname.replace("www.", "") : w;
  }
  if (m.includes("Step 3/4"))               { s[2].status = "running"; s[2].detail = ""; }
  if (m.includes("chars scraped"))          { s[2].status = "done";    s[2].detail = m.replace(/.*Website:\s*/, "").replace("chars scraped", "chars").trim(); }
  if (m.includes("Step 4/4"))               { s[3].status = "running"; s[3].detail = ""; }
  // Per-person enrichment line: "  Name | email | ✓ LinkedIn"
  if (m.match(/\|\s*(—|✓|[a-z0-9._%+@]+)/) && s[3].status === "running") {
    const name = m.split("|")[0].trim();
    if (name) s[3].detail = name;
  }
  return s;
}

// ── Step indicator ──────────────────────────────────────────────────────────

function StepRow({ step, idx }: { step: Step; idx: number }) {
  const isPending = step.status === "pending";
  const isRunning = step.status === "running";
  const isDone    = step.status === "done";

  return (
    <div className="flex items-start gap-3 py-2.5">
      {/* Icon */}
      <div className="flex-shrink-0 mt-0.5">
        {isPending && (
          <div className="w-5 h-5 rounded-full border-2 border-border" />
        )}
        {isRunning && (
          <div className="w-5 h-5 rounded-full border-2 border-blue-600 border-t-transparent animate-spin" />
        )}
        {isDone && (
          <div className="w-5 h-5 rounded-full bg-emerald-600 flex items-center justify-center">
            <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
              <path d="M1 4l2.5 2.5L9 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
        )}
      </div>

      {/* Label + detail */}
      <div className="flex-1 min-w-0">
        <div className={`text-sm font-medium leading-5 ${isPending ? "text-ink3" : "text-ink"}`}>
          {step.label}
        </div>
        {step.detail && (
          <div className="text-xs text-ink2 font-mono mt-0.5 truncate">{step.detail}</div>
        )}
      </div>

      {/* Step number */}
      <div className={`text-xs font-mono flex-shrink-0 mt-0.5 ${isPending ? "text-ink3" : "text-ink3"}`}>
        {idx + 1}/4
      </div>
    </div>
  );
}


// ── Person card ─────────────────────────────────────────────────────────────

function PersonCard({ p, i }: { p: DisplayPerson; i: number }) {
  return (
    <div
      className="bg-surface border border-border rounded-xl p-4 shadow-card hover:shadow-card-md transition-shadow animate-fadeup"
      style={{ animationDelay: `${i * 50}ms` }}
    >
      <div className="flex items-center gap-3 mb-3">
        {/* Avatar */}
        <div className="w-9 h-9 rounded-full bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600 font-semibold text-sm flex-shrink-0">
          {p.full_name.split(" ").map(w => w[0]).slice(0, 2).join("")}
        </div>
        <div className="min-w-0">
          <div className="font-semibold text-ink text-sm leading-5 truncate">{p.full_name}</div>
          <div className="text-xs text-ink2 truncate">{p.title}</div>
        </div>
      </div>

      {/* Company */}
      {p.company && (
        <div className="text-xs text-ink2 mb-3 flex items-center gap-1.5">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="text-ink3 flex-shrink-0">
            <path d="M1 11V3.5L6 1l5 2.5V11M4 11V8h4v3" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
          </svg>
          <span className="truncate">{p.company}</span>
        </div>
      )}

      {/* Contacts */}
      <div className="flex flex-wrap gap-1.5">
        {p.email && (
          <a href={`mailto:${p.email}`}
            className="inline-flex items-center gap-1.5 text-[11px] font-mono text-ink2 bg-s2 border border-border px-2 py-1 rounded-lg hover:border-blue-200 hover:text-blue-600 hover:bg-blue-50 transition-colors">
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><rect x="1" y="2" width="8" height="6" rx="1" stroke="currentColor" strokeWidth="1.1"/><path d="M1 3l4 3 4-3" stroke="currentColor" strokeWidth="1.1"/></svg>
            {p.email}
          </a>
        )}
        {p.phone && (
          <a href={`tel:${p.phone}`}
            className="inline-flex items-center gap-1.5 text-[11px] font-mono text-ink2 bg-s2 border border-border px-2 py-1 rounded-lg hover:border-blue-200 hover:text-blue-600 hover:bg-blue-50 transition-colors">
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M2 2a1 1 0 011-1h1l1 2.5-.75.75a5.5 5.5 0 002.5 2.5L7.5 6 10 7v1a1 1 0 01-1 1c-4.4 0-8-3.6-8-8z" stroke="currentColor" strokeWidth="1"/></svg>
            {p.phone}
          </a>
        )}
        {p.linkedin_url && (
          <a href={p.linkedin_url} target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-[11px] font-mono text-ink2 bg-s2 border border-border px-2 py-1 rounded-lg hover:border-blue-200 hover:text-blue-600 hover:bg-blue-50 transition-colors">
            <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor"><path d="M1 1h2v8H1zM2 0a1 1 0 110 2 1 1 0 010-2zm3 3h1.8v1.1C7.2 3.5 7.9 3 9 3c1.3 0 1 1 1 2.5V9H8V5.5c0-.5-.2-.8-.7-.8-.4 0-.7.3-.7.8V9H4V3z"/></svg>
            LinkedIn
          </a>
        )}
        {!p.email && !p.phone && !p.linkedin_url && (
          <span className="text-[11px] text-ink3">No contact info found</span>
        )}
      </div>
    </div>
  );
}

// ── Main page ───────────────────────────────────────────────────────────────

export default function Home() {
  const [address, setAddress]   = useState("");
  const [model, setModel]       = useState<"2" | "1">("2");
  const [phase, setPhase]       = useState<Phase>("idle");
  const [steps, setSteps]       = useState<Step[]>(INIT_STEPS);
  const [people, setPeople]     = useState<DisplayPerson[]>([]);
  const [company, setCompany]   = useState("");
  const [elapsed, setElapsed]   = useState(0);
  const [liveMsg, setLiveMsg]   = useState("");
  const [error, setError]       = useState("");
  const abortRef                = useRef<AbortController | null>(null);
  const t0Ref                   = useRef<number>(0);
  const timerRef                = useRef<ReturnType<typeof setInterval> | null>(null);

  const startTimer = () => {
    t0Ref.current = Date.now();
    timerRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - t0Ref.current) / 1000));
    }, 1000);
  };
  const stopTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!address.trim()) return;

    setPhase("searching");
    setSteps(INIT_STEPS);
    setPeople([]);
    setCompany("");
    setError("");
    setLiveMsg("");
    setElapsed(0);
    startTimer();

    abortRef.current = new AbortController();
    const endpoint = model === "2" ? "/run/leadership" : "/run/model1";

    try {
      const res = await fetch(`${API_URL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address, model }),
        signal: abortRef.current.signal,
      });
      if (!res.ok) throw new Error(`Server error ${res.status}`);

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error("No response stream");

      let buffer = "";

      const processBlock = (block: string) => {
        const eventMatch = block.match(/^event: (\w+)/m);
        const dataMatch  = block.match(/^data: (.+)/m);
        if (!dataMatch) return;
        const event = eventMatch?.[1] ?? "message";
        let data: Record<string, unknown>;
        try { data = JSON.parse(dataMatch[1]); } catch { return; }

        if (event === "log" || event === "status" || event === "tool") {
          const msg = data.message as string;
          setLiveMsg(msg);
          setSteps(prev => parseLogToStep(msg, prev));
        } else if (event === "done") {
          const raw = (data.leaders as Record<string, unknown>[]) || (data.stakeholders as Record<string, unknown>[]) || [];
          const normalised: DisplayPerson[] = raw.map((r, i) => ({
            rank: (r.rank as number) || i + 1,
            full_name: (r.full_name as string) || "",
            title: (r.title as string) || (r.role as string) || "",
            company: (r.company as string) || "",
            phone: (r.phone as string) || "",
            email: (r.email as string) || "",
            linkedin_url: (r.linkedin_url as string) || "",
            confidence: (r.confidence as string) || (r.confidence_label as string) || "Low",
            property_address: (r.property_address as string) || "",
          }));
          setCompany(normalised[0]?.company || "");
          setPeople(normalised);
          setSteps(prev => prev.map(s => s.status === "running" ? { ...s, status: "done" } : s));
          setPhase("done");
          stopTimer();
        } else if (event === "error") {
          setError(data.message as string);
          setPhase("error");
          stopTimer();
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() ?? "";
        blocks.forEach(processBlock);
      }
      if (buffer.trim()) processBlock(buffer);
      setPhase(p => p === "searching" ? "done" : p);
    } catch (err: unknown) {
      if ((err as Error).name === "AbortError") return;
      const msg = (err as Error).message || "Connection failed";
      setError(msg);
      setPhase("error");
      stopTimer();
    }
  };

  const handleStop = () => {
    abortRef.current?.abort();
    setPhase("idle");
    setLiveMsg("");
    stopTimer();
  };

  const downloadCSV = () => {
    if (!people.length) return;
    const headers = ["rank","full_name","title","company","phone","email","linkedin_url","confidence","property_address"];
    const rows = people.map(p =>
      headers.map(h => `"${((p as Record<string, unknown>)[h] ?? "").toString().replace(/"/g, '""')}"`).join(",")
    );
    const csv = [headers.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `leadership_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const isSearching = phase === "searching";
  const isDone      = phase === "done";
  const runningStep = steps.findIndex(s => s.status === "running");

  return (
    <div className="min-h-screen bg-bg">

      {/* ── Top bar ── */}
      <header className="bg-surface border-b border-border sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-5 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M2 12V5L7 2l5 3v7M5 12V9h4v3" stroke="white" strokeWidth="1.4" strokeLinejoin="round"/>
              </svg>
            </div>
            <span className="font-semibold text-ink tracking-tight">City Scraper</span>
          </div>
          <span className="text-xs text-ink3">Real Estate Intelligence</span>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-5 py-10 space-y-5">

        {/* ── Hero text ── */}
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Find building leadership</h1>
          <p className="text-ink2 text-sm">Enter any property address to find the ownership company and its key contacts.</p>
        </div>

        {/* ── Search card ── */}
        <div className="bg-surface border border-border rounded-2xl shadow-card p-5">
          <form onSubmit={handleSubmit} className="space-y-4">

            <div>
              <label className="block text-xs font-medium text-ink2 mb-1.5">Property address</label>
              <input
                type="text"
                placeholder="30-30 47th Avenue, Long Island City, NY 11101"
                value={address}
                onChange={e => setAddress(e.target.value)}
                disabled={isSearching}
                required
                className="w-full bg-bg border border-border rounded-xl px-3.5 py-2.5 text-sm text-ink placeholder-ink3 transition-all disabled:opacity-50"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-ink2 mb-1.5">Search model</label>
              <div className="flex gap-2">
                {(["2", "1"] as const).map(m => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setModel(m)}
                    disabled={isSearching}
                    className={`flex-1 py-2 px-3 rounded-xl text-xs font-medium border transition-all disabled:opacity-40 text-left ${
                      model === m
                        ? "bg-blue-600 border-blue-600 text-white shadow-sm"
                        : "bg-bg border-border text-ink2 hover:border-borders hover:bg-s2"
                    }`}
                  >
                    <div className="font-semibold">{m === "2" ? "Model 2" : "Model 1"}</div>
                    <div className={`text-[10px] mt-0.5 ${model === m ? "text-blue-100" : "text-ink3"}`}>
                      {m === "2" ? "Leadership — fast · ~20–40s" : "Full stakeholder — deep · ~5min"}
                    </div>
                  </button>
                ))}
              </div>
            </div>

            <div className="flex gap-2.5">
              {isSearching ? (
                <button
                  type="button"
                  onClick={handleStop}
                  className="flex-1 py-2.5 rounded-xl border border-border text-sm font-medium text-ink2 hover:bg-s2 hover:border-borders transition-all"
                >
                  Stop
                </button>
              ) : (
                <button
                  type="submit"
                  className="flex-1 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold transition-colors shadow-sm"
                >
                  Run search
                </button>
              )}
            </div>
          </form>
        </div>

        {/* ── Progress card ── */}
        {(isSearching || (isDone && people.length === 0 && !error)) && (
          <div className="bg-surface border border-border rounded-2xl shadow-card p-5 animate-fadeup">
            <div className="flex items-center justify-between mb-4">
              <div className="text-sm font-semibold text-ink">Search progress</div>
              {isSearching && (
                <div className="flex items-center gap-1.5 text-xs text-ink3 font-mono">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse inline-block" />
                  {elapsed}s
                </div>
              )}
            </div>

            <div className="divide-y divide-border">
              {steps.map((step, i) => <StepRow key={i} step={step} idx={i} />)}
            </div>

            {isSearching && runningStep >= 0 && liveMsg && (
              <div className="mt-3 pt-3 border-t border-border">
                <p className="text-[11px] text-ink3 font-mono truncate">{liveMsg}</p>
              </div>
            )}
          </div>
        )}

        {/* ── Error ── */}
        {phase === "error" && error && (
          <div className="bg-rose-50 border border-rose-100 rounded-2xl p-4 animate-fadeup">
            <div className="flex items-start gap-2.5">
              <div className="w-5 h-5 rounded-full bg-rose-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                  <path d="M5 3v3M5 7.5v.5" stroke="#E11D48" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
              </div>
              <div>
                <div className="text-sm font-medium text-rose-700 mb-0.5">Search failed</div>
                <div className="text-xs text-rose-600">{error}</div>
              </div>
            </div>
          </div>
        )}

        {/* ── Done: summary bar ── */}
        {isDone && (
          <div className="animate-fadeup">
            <div className="bg-surface border border-border rounded-2xl shadow-card overflow-hidden">
              {/* Summary header */}
              <div className="flex items-center justify-between px-5 py-4 border-b border-border">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-ink">
                      {people.length > 0 ? `${people.length} people found` : "No results"}
                    </span>
                    {company && (
                      <>
                        <span className="text-ink3 text-sm">·</span>
                        <span className="text-sm text-ink2">{company}</span>
                      </>
                    )}
                    <span className="text-ink3 text-sm">·</span>
                    <span className="text-xs text-ink3 font-mono">{elapsed}s</span>
                  </div>
                  <div className="text-xs text-ink3 mt-0.5 truncate">{address}</div>
                </div>
                {people.length > 0 && (
                  <button
                    onClick={downloadCSV}
                    className="flex items-center gap-1.5 text-xs font-medium text-ink2 bg-s2 border border-border px-3 py-1.5 rounded-lg hover:bg-border hover:text-ink transition-colors flex-shrink-0 ml-3"
                  >
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                      <path d="M6 1v7M3 5l3 3 3-3M1 10h10" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                    CSV
                  </button>
                )}
              </div>

            </div>
          </div>
        )}

        {/* ── People grid ── */}
        {isDone && people.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 animate-fadeup">
            {people.map((p, i) => <PersonCard key={i} p={p} i={i} />)}
          </div>
        )}

        {/* ── Empty state ── */}
        {isDone && people.length === 0 && (
          <div className="bg-surface border border-border rounded-2xl p-10 text-center animate-fadeup">
            <div className="w-10 h-10 rounded-full bg-s2 flex items-center justify-center mx-auto mb-3">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="9" r="7" stroke="#94A3B8" strokeWidth="1.5"/>
                <path d="M9 6v4M9 12v.5" stroke="#94A3B8" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
            </div>
            <div className="text-sm font-medium text-ink mb-1">No contacts found</div>
            <div className="text-xs text-ink3 max-w-xs mx-auto">
              The pipeline ran but couldn't find leadership data for this address. Try a different address or check the building owner manually.
            </div>
          </div>
        )}

      </main>

      {/* ── Footer ── */}
      <footer className="border-t border-border mt-16 py-5">
        <div className="max-w-3xl mx-auto px-5 flex items-center justify-between text-[11px] text-ink3">
          <span>City Scraper · Real Estate Intelligence</span>
          <span className="font-mono">Powered by Claude · Public Records · DDG</span>
        </div>
      </footer>

    </div>
  );
}
