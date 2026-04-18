"use client";

import { useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, MapPin, ChevronRight, AlertCircle, Download } from "lucide-react";
import dynamic from "next/dynamic";
import ResultsTable from "@/components/ResultsTable";
import Detective from "@/components/Detective";

// Canvas-heavy component — client only, no SSR
const CityScene = dynamic(() => import("@/components/CityScene"), { ssr: false });

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Stakeholder {
  role: string;
  full_name: string;
  company: string;
  phone: string;
  email: string;
  linkedin_url: string;
  website: string;
  confidence_score: number;
  confidence_label: string;
  sources: string;
  permit_number: string;
  permit_type: string;
  notes: string;
  property_address: string;
}

interface LogEntry {
  id: string;
  message: string;
  step: string;
  ts: number;
}

type Phase = "idle" | "searching" | "done" | "error";

const STEP_ICONS: Record<string, string> = {
  init:    "🔍",
  permits: "🏛️",
  owner:   "🏠",
  company: "🔎",
  web:     "🌐",
  google:  "🔎",
  linkedin:"👤",
  email:   "📧",
  done:    "✅",
  error:   "❌",
};

export default function Home() {
  const [form, setForm] = useState({ address: "", city: "New York", state: "NY", zip_code: "" });
  const [phase, setPhase] = useState<Phase>("idle");
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [currentMsg, setCurrentMsg] = useState("");
  const [toolCount, setToolCount] = useState(0);
  const [stakeholders, setStakeholders] = useState<Stakeholder[]>([]);
  const [error, setError] = useState("");
  const logsEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const pushLog = (message: string, step: string) => {
    setLogs((prev) => [
      ...prev,
      { id: `${Date.now()}-${Math.random()}`, message, step, ts: Date.now() },
    ]);
    setTimeout(() => logsEndRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.address.trim() || !form.city.trim()) return;

    // Reset state
    setPhase("searching");
    setLogs([]);
    setCurrentMsg("");
    setToolCount(0);
    setStakeholders([]);
    setError("");

    abortRef.current = new AbortController();

    try {
      const res = await fetch(`${API_URL}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
        signal: abortRef.current.signal,
      });

      if (!res.ok) {
        throw new Error(`Server error ${res.status}`);
      }

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      if (!reader) throw new Error("No response stream");

      const processBlock = (block: string) => {
        const eventMatch = block.match(/^event: (\w+)/m);
        const dataMatch = block.match(/^data: (.+)/m);
        if (!dataMatch) return;
        const event = eventMatch?.[1] ?? "message";
        let data: Record<string, unknown>;
        try { data = JSON.parse(dataMatch[1]); } catch { return; }

        if (event === "status") {
          const msg = data.message as string;
          setCurrentMsg(msg);
          pushLog(msg, (data.step as string) || "init");
        } else if (event === "tool") {
          const msg = data.message as string;
          const cnt = (data.count as number) || 0;
          setCurrentMsg(msg);
          setToolCount(cnt);
          pushLog(msg, (data.step as string) || "tool");
        } else if (event === "done") {
          const items = (data.stakeholders as Stakeholder[]) || [];
          setStakeholders(items);
          setPhase("done");
          setCurrentMsg(`Found ${items.length} stakeholders`);
          pushLog(`✅ Complete — ${items.length} stakeholders found`, "done");
        } else if (event === "error") {
          const msg = data.message as string;
          setError(msg);
          setPhase("error");
          pushLog(`❌ ${msg}`, "error");
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        // SSE blocks are separated by double newline
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() ?? "";
        blocks.forEach(processBlock);
      }
      // Process any remaining buffer
      if (buffer.trim()) processBlock(buffer);

      setPhase((p) => p === "searching" ? "done" : p);
    } catch (err: unknown) {
      if ((err as Error).name === "AbortError") return;
      const msg = (err as Error).message || "Connection failed";
      setError(msg);
      setPhase("error");
      pushLog(`❌ ${msg}`, "error");
    }
  };

  const handleStop = () => {
    abortRef.current?.abort();
    setPhase("idle");
    setCurrentMsg("");
  };

  const downloadCSV = () => {
    if (!stakeholders.length) return;
    const headers = ["role","full_name","company","phone","email","linkedin_url","website","confidence_score","confidence_label","sources","permit_number","permit_type","notes","property_address"];
    const rows = stakeholders.map((s) =>
      headers.map((h) => `"${(s[h as keyof Stakeholder] ?? "").toString().replace(/"/g, '""')}"`).join(",")
    );
    const csv = [headers.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "stakeholders.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const isSearching = phase === "searching";
  const isDone = phase === "done";

  return (
    <main className="min-h-screen flex flex-col">
      {/* ── City scene hero ── */}
      <section className="relative h-[420px] overflow-hidden flex-shrink-0">
        <CityScene active={isSearching} />

        {/* Gradient fade to page bg */}
        <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-night-950 to-transparent" />

        {/* Hero headline */}
        <div className="absolute inset-x-0 top-8 flex flex-col items-center pointer-events-none">
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-[10px] font-mono tracking-[0.3em] text-neon-cyan/60 uppercase mb-2"
          >
            Real Estate Intelligence
          </motion.div>
          <motion.h1
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="font-display font-bold text-4xl md:text-5xl text-white glow-cyan text-center leading-tight"
          >
            City Scraper
          </motion.h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
            className="text-slate-400 text-sm mt-2 font-mono"
          >
            Find every stakeholder behind any property address
          </motion.p>
        </div>

        {/* Detective character — positioned on the street */}
        <div className="absolute bottom-8 right-[12%] md:right-[18%]">
          <Detective
            phase={phase === "error" ? "idle" : phase}
            currentStep={currentMsg}
            toolCount={toolCount}
          />
        </div>
      </section>

      {/* ── Content area ── */}
      <div className="flex-1 bg-night-950">
        <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">

          {/* Search form */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="glass rounded-2xl p-6 border-glow-cyan"
          >
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="flex items-center gap-2 mb-1">
                <MapPin size={16} className="text-neon-cyan" />
                <span className="font-display font-semibold text-white">Property Address</span>
              </div>

              {/* Address */}
              <input
                type="text"
                placeholder="350 5th Ave"
                value={form.address}
                onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))}
                disabled={isSearching}
                required
                className="w-full bg-night-800 border border-night-700 rounded-xl px-4 py-3 text-white placeholder-slate-600 font-mono text-sm focus:border-neon-cyan/60 focus:ring-1 focus:ring-neon-cyan/30 transition-all disabled:opacity-50"
              />

              {/* City / State / ZIP row */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <input
                  type="text"
                  placeholder="City"
                  value={form.city}
                  onChange={(e) => setForm((f) => ({ ...f, city: e.target.value }))}
                  disabled={isSearching}
                  required
                  className="bg-night-800 border border-night-700 rounded-xl px-4 py-3 text-white placeholder-slate-600 font-mono text-sm focus:border-neon-cyan/60 focus:ring-1 focus:ring-neon-cyan/30 transition-all disabled:opacity-50"
                />
                <input
                  type="text"
                  placeholder="State (NY)"
                  value={form.state}
                  onChange={(e) => setForm((f) => ({ ...f, state: e.target.value }))}
                  disabled={isSearching}
                  className="bg-night-800 border border-night-700 rounded-xl px-4 py-3 text-white placeholder-slate-600 font-mono text-sm focus:border-neon-cyan/60 focus:ring-1 focus:ring-neon-cyan/30 transition-all disabled:opacity-50"
                />
                <input
                  type="text"
                  placeholder="ZIP (optional)"
                  value={form.zip_code}
                  onChange={(e) => setForm((f) => ({ ...f, zip_code: e.target.value }))}
                  disabled={isSearching}
                  className="col-span-2 sm:col-span-1 bg-night-800 border border-night-700 rounded-xl px-4 py-3 text-white placeholder-slate-600 font-mono text-sm focus:border-neon-cyan/60 focus:ring-1 focus:ring-neon-cyan/30 transition-all disabled:opacity-50"
                />
              </div>

              {/* Submit / Stop */}
              <div className="flex gap-3">
                {isSearching ? (
                  <button
                    type="button"
                    onClick={handleStop}
                    className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl border border-red-500/50 text-red-400 hover:bg-red-500/10 transition-all font-display font-medium"
                  >
                    Stop Search
                  </button>
                ) : (
                  <button
                    type="submit"
                    className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl bg-neon-cyan/10 border border-neon-cyan/50 text-neon-cyan hover:bg-neon-cyan/20 hover:shadow-[0_0_20px_#00f5ff33] transition-all font-display font-semibold"
                  >
                    <Search size={16} />
                    Investigate
                    <ChevronRight size={14} className="opacity-60" />
                  </button>
                )}
              </div>
            </form>
          </motion.div>

          {/* Live activity log */}
          <AnimatePresence>
            {logs.length > 0 && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="glass rounded-2xl overflow-hidden"
              >
                <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
                  <span className="text-xs font-mono text-slate-400 tracking-wider uppercase">
                    Agent Activity
                  </span>
                  {isSearching && (
                    <span className="flex items-center gap-1.5 text-xs font-mono text-neon-cyan">
                      <span className="w-2 h-2 rounded-full bg-neon-cyan animate-pulse" />
                      Live
                    </span>
                  )}
                </div>
                <div className="max-h-48 overflow-y-auto p-3 space-y-1">
                  {logs.map((log) => (
                    <motion.div
                      key={log.id}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      className="flex items-start gap-2 text-xs font-mono py-0.5"
                    >
                      <span className="text-base leading-none flex-shrink-0">
                        {STEP_ICONS[log.step] || "⚙️"}
                      </span>
                      <span className={log.step === "error" ? "text-red-400" : log.step === "done" ? "text-neon-green" : "text-slate-300"}>
                        {log.message}
                      </span>
                    </motion.div>
                  ))}
                  <div ref={logsEndRef} />
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Error */}
          <AnimatePresence>
            {phase === "error" && error && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="flex items-start gap-3 p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm font-mono"
              >
                <AlertCircle size={16} className="flex-shrink-0 mt-0.5" />
                <span>{error}</span>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Results */}
          <AnimatePresence>
            {isDone && stakeholders.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="space-y-4"
              >
                {/* Download button */}
                <div className="flex justify-end">
                  <button
                    onClick={downloadCSV}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl glass border border-neon-green/30 text-neon-green text-xs font-mono hover:bg-neon-green/10 transition-all"
                  >
                    <Download size={13} />
                    Export CSV
                  </button>
                </div>

                <ResultsTable stakeholders={stakeholders} />
              </motion.div>
            )}
          </AnimatePresence>

          {/* Empty done state */}
          <AnimatePresence>
            {isDone && stakeholders.length === 0 && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="text-center py-12 text-slate-500 font-mono text-sm"
              >
                No stakeholders found for this address.<br />
                <span className="text-xs text-slate-600">The agent may have hit its tool limit or the address returned no permit records.</span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Footer */}
      <footer className="py-4 text-center text-[11px] font-mono text-slate-700 bg-night-950">
        City Scraper · Powered by Claude · NYC DOB · Exa.ai
      </footer>
    </main>
  );
}
