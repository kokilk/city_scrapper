"use client";

import { motion, AnimatePresence } from "framer-motion";

interface DetectiveProps {
  phase: "idle" | "searching" | "done";
  currentStep: string;
  toolCount: number;
}

export default function Detective({ phase, currentStep, toolCount }: DetectiveProps) {
  const isSearching = phase === "searching";
  const isDone = phase === "done";

  return (
    <div className="relative flex flex-col items-center">
      {/* Speech bubble */}
      <AnimatePresence mode="wait">
        {currentStep && (
          <motion.div
            key={currentStep}
            initial={{ opacity: 0, y: 8, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.9 }}
            transition={{ duration: 0.3 }}
            className="absolute -top-16 left-1/2 -translate-x-1/2 w-64 glass rounded-xl px-3 py-2 text-xs font-mono text-neon-cyan text-center border border-neon-cyan/30 whitespace-nowrap overflow-hidden text-ellipsis"
            style={{ boxShadow: "0 0 12px #00f5ff33" }}
          >
            {currentStep}
            {/* Bubble tail */}
            <div
              className="absolute -bottom-2 left-1/2 -translate-x-1/2 w-3 h-3 rotate-45 glass border-r border-b border-neon-cyan/30"
              style={{ background: "rgba(15,23,42,0.7)" }}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Counter badge */}
      {isSearching && toolCount > 0 && (
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-neon-purple text-white text-[10px] font-bold flex items-center justify-center z-10"
          style={{ boxShadow: "0 0 8px #bf00ff" }}
        >
          {toolCount}
        </motion.div>
      )}

      {/* Detective SVG character */}
      <motion.div
        animate={
          isDone
            ? { scale: [1, 1.15, 0.95, 1.05, 1], rotate: [0, -8, 8, -4, 0] }
            : isSearching
            ? { y: [0, -4, 0] }
            : { y: [0, -2, 0] }
        }
        transition={
          isDone
            ? { duration: 0.7, ease: "easeInOut" }
            : { duration: isSearching ? 0.8 : 2, repeat: Infinity, ease: "easeInOut" }
        }
      >
        <svg width="80" height="120" viewBox="0 0 80 120" fill="none">
          {/* Shadow */}
          <ellipse cx="40" cy="115" rx="18" ry="4" fill="rgba(0,245,255,0.15)" />

          {/* Coat / body */}
          <motion.g
            animate={isSearching ? { skewX: [-2, 2, -2] } : {}}
            transition={{ duration: 0.4, repeat: Infinity, ease: "easeInOut" }}
          >
            {/* Trench coat */}
            <path d="M22 65 L15 105 L38 100 L40 85 L42 100 L65 105 L58 65 Z" fill="#1e2d4a" />
            <path d="M22 65 L18 105 L38 100 L40 85 L42 100 L62 105 L58 65 Z" stroke="#00f5ff33" strokeWidth="1" />
            {/* Coat lapels */}
            <path d="M33 65 L28 80 L40 72 L52 80 L47 65 Z" fill="#0f172a" stroke="#00f5ff22" strokeWidth="0.5" />
            {/* Coat belt */}
            <rect x="30" y="82" width="20" height="3" rx="1" fill="#00f5ff33" />
            {/* Coat buttons */}
            <circle cx="40" cy="90" r="1.5" fill="#ffd70066" />
            <circle cx="40" cy="96" r="1.5" fill="#ffd70066" />
          </motion.g>

          {/* Left leg */}
          <motion.g
            animate={isSearching ? { rotate: [-15, 15] } : {}}
            transition={{ duration: 0.4, repeat: Infinity, ease: "easeInOut", repeatType: "reverse" }}
            style={{ transformOrigin: "30px 98px" }}
          >
            <rect x="26" y="98" width="9" height="16" rx="3" fill="#0f172a" />
            {/* Shoe */}
            <ellipse cx="28" cy="114" rx="7" ry="3.5" fill="#030712" />
            <ellipse cx="29" cy="113" rx="5" ry="2.5" fill="#1e2d4a" />
          </motion.g>

          {/* Right leg */}
          <motion.g
            animate={isSearching ? { rotate: [15, -15] } : {}}
            transition={{ duration: 0.4, repeat: Infinity, ease: "easeInOut", repeatType: "reverse" }}
            style={{ transformOrigin: "50px 98px" }}
          >
            <rect x="45" y="98" width="9" height="16" rx="3" fill="#0f172a" />
            {/* Shoe */}
            <ellipse cx="52" cy="114" rx="7" ry="3.5" fill="#030712" />
            <ellipse cx="51" cy="113" rx="5" ry="2.5" fill="#1e2d4a" />
          </motion.g>

          {/* Left arm */}
          <motion.g
            animate={isSearching ? { rotate: [10, -10] } : {}}
            transition={{ duration: 0.4, repeat: Infinity, ease: "easeInOut", repeatType: "reverse" }}
            style={{ transformOrigin: "22px 68px" }}
          >
            <rect x="12" y="68" width="10" height="20" rx="4" fill="#1e2d4a" />
            {/* Hand */}
            <circle cx="17" cy="89" r="4.5" fill="#fbbf24" />
          </motion.g>

          {/* Right arm with magnifier */}
          <motion.g
            animate={isSearching ? { rotate: [-20, 20] } : {}}
            transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut", repeatType: "reverse" }}
            style={{ transformOrigin: "58px 68px" }}
          >
            <rect x="58" y="68" width="10" height="22" rx="4" fill="#1e2d4a" />
            {/* Hand */}
            <circle cx="63" cy="91" r="4.5" fill="#fbbf24" />
            {/* Magnifying glass */}
            <circle cx="68" cy="96" r="8" fill="none" stroke="#00f5ff" strokeWidth="2" />
            <circle cx="68" cy="96" r="5" fill="rgba(0,245,255,0.1)" />
            {/* Lens glint */}
            <circle cx="65" cy="93" r="1.5" fill="rgba(255,255,255,0.4)" />
            <line x1="74" y1="102" x2="79" y2="108" stroke="#00f5ff" strokeWidth="2.5" strokeLinecap="round" />
          </motion.g>

          {/* Neck */}
          <rect x="36" y="50" width="8" height="10" rx="2" fill="#fbbf24" />

          {/* Head */}
          <ellipse cx="40" cy="40" rx="17" ry="18" fill="#fbbf24" />
          {/* Face shading */}
          <ellipse cx="40" cy="43" rx="13" ry="12" fill="#f59e0b" opacity="0.4" />

          {/* Eyes */}
          <motion.g
            animate={isSearching ? { scaleY: [1, 0.1, 1] } : { scaleY: [1, 0.1, 1] }}
            transition={
              isSearching
                ? { duration: 0.3, repeat: Infinity, repeatDelay: 1.5 }
                : { duration: 0.2, repeat: Infinity, repeatDelay: 3 }
            }
            style={{ transformOrigin: "40px 38px" }}
          >
            <ellipse cx="33" cy="38" rx="4" ry="4.5" fill="white" />
            <ellipse cx="47" cy="38" rx="4" ry="4.5" fill="white" />
          </motion.g>
          {/* Pupils */}
          <motion.g
            animate={isSearching ? { x: [-1, 1, -1], y: [-1, 0.5, -1] } : {}}
            transition={{ duration: 0.6, repeat: Infinity, ease: "easeInOut" }}
          >
            <circle cx="34" cy="38" r="2.5" fill="#0f172a" />
            <circle cx="48" cy="38" r="2.5" fill="#0f172a" />
            {/* Pupils shine */}
            <circle cx="35" cy="37" r="1" fill="white" />
            <circle cx="49" cy="37" r="1" fill="white" />
          </motion.g>

          {/* Eyebrows — furrowed when searching */}
          <motion.g
            animate={isSearching ? { y: -2 } : { y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <path d="M29 31 Q33 29 37 31" stroke="#92400e" strokeWidth="2" strokeLinecap="round" fill="none" />
            <path d="M43 31 Q47 29 51 31" stroke="#92400e" strokeWidth="2" strokeLinecap="round" fill="none" />
          </motion.g>

          {/* Nose */}
          <path d="M38 43 Q40 47 42 43" stroke="#92400e" strokeWidth="1.5" strokeLinecap="round" fill="none" />

          {/* Mouth */}
          <motion.path
            d={isDone ? "M34 50 Q40 56 46 50" : isSearching ? "M35 50 Q40 49 45 50" : "M34 50 Q40 54 46 50"}
            stroke="#92400e"
            strokeWidth="2"
            strokeLinecap="round"
            fill="none"
            animate={{ d: isDone ? "M34 50 Q40 56 46 50" : isSearching ? "M35 50 Q40 49 45 50" : "M34 50 Q40 54 46 50" }}
            transition={{ duration: 0.4 }}
          />

          {/* Hat */}
          <rect x="22" y="22" width="36" height="6" rx="2" fill="#0f172a" />
          <rect x="26" y="8" width="28" height="16" rx="3" fill="#0f172a" />
          {/* Hat band */}
          <rect x="26" y="20" width="28" height="3" fill="#00f5ff33" />
          {/* Hat highlight */}
          <rect x="28" y="10" width="8" height="3" rx="1" fill="rgba(0,245,255,0.15)" />

          {/* Done sparkles */}
          {isDone && (
            <>
              <motion.circle
                cx="10" cy="20" r="3"
                fill="#ffd700"
                animate={{ scale: [0, 1.5, 0], opacity: [0, 1, 0] }}
                transition={{ duration: 0.8, delay: 0.1, repeat: 3 }}
              />
              <motion.circle
                cx="70" cy="15" r="2.5"
                fill="#00ff88"
                animate={{ scale: [0, 1.5, 0], opacity: [0, 1, 0] }}
                transition={{ duration: 0.8, delay: 0.3, repeat: 3 }}
              />
              <motion.circle
                cx="15" cy="60" r="2"
                fill="#00f5ff"
                animate={{ scale: [0, 1.5, 0], opacity: [0, 1, 0] }}
                transition={{ duration: 0.8, delay: 0.2, repeat: 3 }}
              />
              <motion.circle
                cx="68" cy="55" r="3"
                fill="#bf00ff"
                animate={{ scale: [0, 1.5, 0], opacity: [0, 1, 0] }}
                transition={{ duration: 0.8, delay: 0.4, repeat: 3 }}
              />
            </>
          )}
        </svg>
      </motion.div>

      {/* Phase label */}
      <div className="mt-2 text-[10px] font-mono tracking-widest uppercase">
        {isDone ? (
          <span className="text-neon-green glow-green">Case Solved!</span>
        ) : isSearching ? (
          <span className="text-neon-cyan animate-pulse">Investigating...</span>
        ) : (
          <span className="text-night-700">Ready</span>
        )}
      </div>
    </div>
  );
}
