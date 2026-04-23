import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg:      "#F7F8FA",
        surface: "#FFFFFF",
        s2:      "#F1F4F9",
        border:  "#E2E8F0",
        borders: "#CBD5E1",
        ink:     "#0F172A",
        ink2:    "#475569",
        ink3:    "#94A3B8",
        blue: {
          50:  "#EFF6FF",
          100: "#DBEAFE",
          200: "#BFDBFE",
          500: "#3B82F6",
          600: "#2563EB",
          700: "#1D4ED8",
        },
        emerald: {
          50:  "#ECFDF5",
          100: "#D1FAE5",
          600: "#059669",
          700: "#047857",
        },
        amber: {
          50:  "#FFFBEB",
          100: "#FEF3C7",
          600: "#D97706",
          700: "#B45309",
        },
        rose: {
          50:  "#FFF1F2",
          100: "#FFE4E6",
          600: "#E11D48",
        },
      },
      fontFamily: {
        sans: ["'Inter'", "system-ui", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
      boxShadow: {
        card:      "0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)",
        "card-md": "0 4px 12px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.04)",
        "card-lg": "0 8px 24px rgba(0,0,0,0.08), 0 2px 8px rgba(0,0,0,0.04)",
      },
      keyframes: {
        spin:   { to: { transform: "rotate(360deg)" } },
        fadeup: { "0%": { opacity: "0", transform: "translateY(8px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        fadein: { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        pulse:  { "0%,100%": { opacity: "1" }, "50%": { opacity: "0.4" } },
      },
      animation: {
        spin:   "spin 0.7s linear infinite",
        fadeup: "fadeup 0.35s ease-out both",
        fadein: "fadein 0.25s ease-out both",
        pulse:  "pulse 1.5s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
