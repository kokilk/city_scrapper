import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        night: {
          950: "#030712",
          900: "#0a0f1e",
          800: "#0f172a",
          700: "#1e2d4a",
        },
        neon: {
          cyan:   "#00f5ff",
          purple: "#bf00ff",
          gold:   "#ffd700",
          green:  "#00ff88",
          orange: "#ff6b00",
        },
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        mono:    ["'JetBrains Mono'", "monospace"],
      },
      keyframes: {
        float:     { "0%,100%": { transform: "translateY(0px)" }, "50%": { transform: "translateY(-8px)" } },
        blink:     { "0%,90%,100%": { opacity: "1" }, "95%": { opacity: "0" } },
        scanline:  { "0%": { transform: "translateY(-100%)" }, "100%": { transform: "translateY(100vh)" } },
        citylight: { "0%,100%": { opacity: "0.4" }, "50%": { opacity: "1" } },
        walk:      { "0%,100%": { transform: "rotate(-15deg)" }, "50%": { transform: "rotate(15deg)" } },
        walktop:   { "0%,100%": { transform: "rotate(10deg)" },  "50%": { transform: "rotate(-10deg)" } },
        bob:       { "0%,100%": { transform: "translateY(0)" },  "50%": { transform: "translateY(-3px)" } },
        magnify:   { "0%,100%": { transform: "rotate(-20deg) scale(1)" }, "50%": { transform: "rotate(20deg) scale(1.1)" } },
        shimmer:   { "0%": { backgroundPosition: "-200% 0" }, "100%": { backgroundPosition: "200% 0" } },
        pulse2:    { "0%,100%": { boxShadow: "0 0 10px #00f5ff44" }, "50%": { boxShadow: "0 0 30px #00f5ffaa, 0 0 60px #00f5ff44" } },
        celebrate: { "0%": { transform: "scale(1) rotate(0deg)" }, "25%": { transform: "scale(1.2) rotate(-10deg)" }, "50%": { transform: "scale(1.3) rotate(10deg)" }, "75%": { transform: "scale(1.1) rotate(-5deg)" }, "100%": { transform: "scale(1) rotate(0deg)" } },
        slide:     { "0%": { transform: "translateX(-100%)", opacity: "0" }, "100%": { transform: "translateX(0)", opacity: "1" } },
        fadeup:    { "0%": { transform: "translateY(20px)", opacity: "0" }, "100%": { transform: "translateY(0)", opacity: "1" } },
      },
      animation: {
        float:     "float 3s ease-in-out infinite",
        blink:     "blink 4s infinite",
        walk:      "walk 0.4s ease-in-out infinite",
        walktop:   "walktop 0.4s ease-in-out infinite",
        bob:       "bob 1s ease-in-out infinite",
        magnify:   "magnify 1.5s ease-in-out infinite",
        shimmer:   "shimmer 2s linear infinite",
        pulse2:    "pulse2 2s ease-in-out infinite",
        celebrate: "celebrate 0.6s ease-in-out",
        slide:     "slide 0.5s ease-out",
        fadeup:    "fadeup 0.5s ease-out",
        citylight: "citylight 3s ease-in-out infinite",
        scanline:  "scanline 8s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
