"use client";

import { motion } from "framer-motion";
import { ExternalLink, Phone, Mail, Linkedin, Globe, Building2, User, Hammer, Home, Banknote, Wrench } from "lucide-react";

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

const ROLE_ICONS: Record<string, React.ReactNode> = {
  Developer: <Building2 size={14} />,
  Architect: <User size={14} />,
  "General Contractor": <Hammer size={14} />,
  GC: <Hammer size={14} />,
  Owner: <Home size={14} />,
  Lender: <Banknote size={14} />,
  Subcontractor: <Wrench size={14} />,
};

const ROLE_COLORS: Record<string, string> = {
  Developer: "text-neon-cyan border-neon-cyan/40 bg-neon-cyan/10",
  Architect: "text-neon-purple border-neon-purple/40 bg-neon-purple/10",
  "General Contractor": "text-neon-orange border-neon-orange/40 bg-neon-orange/10",
  GC: "text-neon-orange border-neon-orange/40 bg-neon-orange/10",
  Owner: "text-neon-gold border-neon-gold/40 bg-neon-gold/10",
  Lender: "text-neon-green border-neon-green/40 bg-neon-green/10",
  Subcontractor: "text-slate-400 border-slate-400/40 bg-slate-400/10",
};

function ConfidenceBadge({ score, label }: { score: number; label: string }) {
  const color =
    score >= 75 ? "text-neon-green" : score >= 45 ? "text-neon-gold" : "text-slate-400";
  const bg =
    score >= 75 ? "bg-neon-green/10 border-neon-green/30" : score >= 45 ? "bg-neon-gold/10 border-neon-gold/30" : "bg-slate-800 border-slate-600";

  return (
    <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[11px] font-mono ${bg}`}>
      <div className={`w-1.5 h-1.5 rounded-full ${color.replace("text-", "bg-")}`} />
      <span className={color}>{label || (score >= 75 ? "Verified" : score >= 45 ? "Probable" : "Unconfirmed")}</span>
      <span className="text-slate-500">{score}%</span>
    </div>
  );
}

function ContactChip({ href, label, icon }: { href: string; label: string; icon: React.ReactNode }) {
  if (!label || label === "N/A") return null;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center gap-1 px-2 py-0.5 rounded glass text-[11px] text-slate-300 hover:text-neon-cyan hover:border-neon-cyan/40 transition-colors border border-slate-700/50"
    >
      <span className="text-neon-cyan/70">{icon}</span>
      <span className="max-w-[120px] truncate">{label}</span>
      <ExternalLink size={9} className="opacity-50 flex-shrink-0" />
    </a>
  );
}

interface ResultsTableProps {
  stakeholders: Stakeholder[];
}

export default function ResultsTable({ stakeholders }: ResultsTableProps) {
  if (!stakeholders.length) return null;

  return (
    <div className="w-full space-y-3">
      <div className="flex items-center gap-3 mb-4">
        <h2 className="font-display font-semibold text-lg text-white">
          Stakeholders Found
        </h2>
        <span className="px-2.5 py-0.5 rounded-full text-xs font-mono bg-neon-cyan/10 border border-neon-cyan/30 text-neon-cyan">
          {stakeholders.length} contacts
        </span>
      </div>

      {stakeholders.map((s, i) => {
        const roleKey = Object.keys(ROLE_COLORS).find((k) => s.role?.toLowerCase().includes(k.toLowerCase())) || "Subcontractor";
        const roleColor = ROLE_COLORS[roleKey] || ROLE_COLORS.Subcontractor;
        const roleIcon = ROLE_ICONS[roleKey] || ROLE_ICONS.Subcontractor;

        return (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.08 }}
            className="glass rounded-xl p-4 border border-white/5 hover:border-neon-cyan/20 transition-colors group"
          >
            <div className="flex flex-col sm:flex-row sm:items-start gap-3">
              {/* Role badge */}
              <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-mono font-medium self-start flex-shrink-0 ${roleColor}`}>
                {roleIcon}
                {s.role || "Unknown"}
              </div>

              <div className="flex-1 min-w-0">
                {/* Name & company */}
                <div className="flex flex-wrap items-baseline gap-2 mb-2">
                  <span className="font-display font-semibold text-white text-base">
                    {s.full_name || "—"}
                  </span>
                  {s.company && (
                    <span className="text-sm text-slate-400 truncate">{s.company}</span>
                  )}
                </div>

                {/* Contacts row */}
                <div className="flex flex-wrap gap-1.5 mb-2.5">
                  <ContactChip href={`tel:${s.phone}`} label={s.phone} icon={<Phone size={10} />} />
                  <ContactChip href={`mailto:${s.email}`} label={s.email} icon={<Mail size={10} />} />
                  <ContactChip href={s.linkedin_url} label={s.linkedin_url ? "LinkedIn" : ""} icon={<Linkedin size={10} />} />
                  <ContactChip href={s.website?.startsWith("http") ? s.website : `https://${s.website}`} label={s.website} icon={<Globe size={10} />} />
                </div>

                {/* Meta row */}
                <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500 font-mono">
                  <ConfidenceBadge score={s.confidence_score || 0} label={s.confidence_label} />
                  {s.sources && (
                    <span className="flex items-center gap-1">
                      <span className="text-slate-600">src:</span>
                      <span className="text-slate-400">{s.sources}</span>
                    </span>
                  )}
                  {s.permit_number && (
                    <span className="flex items-center gap-1">
                      <span className="text-slate-600">permit:</span>
                      <span className="text-neon-gold/60">{s.permit_number}</span>
                    </span>
                  )}
                  {s.permit_type && (
                    <span className="text-slate-500">{s.permit_type}</span>
                  )}
                  {s.notes && s.notes !== "" && (
                    <span className="text-slate-500 italic">{s.notes}</span>
                  )}
                </div>
              </div>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
