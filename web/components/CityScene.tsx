"use client";

import { useEffect, useRef } from "react";

interface WindowLight {
  x: number;
  y: number;
  w: number;
  h: number;
  color: string;
  delay: number;
}

interface Building {
  x: number;
  w: number;
  h: number;
  color: string;
  windows: WindowLight[];
  hasAntenna: boolean;
}

function randomWindows(bx: number, bw: number, bh: number, baseY: number): WindowLight[] {
  const cols = Math.floor(bw / 14);
  const rows = Math.floor(bh / 18);
  const wins: WindowLight[] = [];
  const colors = ["#00f5ff", "#ffd700", "#ff6b00", "#00ff88", "#bf00ff", "#ffffff"];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (Math.random() > 0.35) {
        wins.push({
          x: bx + 4 + c * 14,
          y: baseY - bh + 6 + r * 18,
          w: 8,
          h: 10,
          color: colors[Math.floor(Math.random() * colors.length)],
          delay: Math.random() * 4,
        });
      }
    }
  }
  return wins;
}

function generateBuildings(canvasW: number, groundY: number): Building[] {
  const buildings: Building[] = [];
  const palette = ["#0a0f1e", "#0f172a", "#0d1829", "#111827", "#0c1523"];
  let x = -20;
  while (x < canvasW + 60) {
    const w = 45 + Math.random() * 70;
    const h = 80 + Math.random() * 220;
    const color = palette[Math.floor(Math.random() * palette.length)];
    buildings.push({
      x,
      w,
      h,
      color,
      windows: randomWindows(x, w, h, groundY),
      hasAntenna: Math.random() > 0.5,
    });
    x += w + 4 + Math.random() * 8;
  }
  return buildings;
}

export default function CityScene({ active }: { active: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef<number>(0);
  const tickRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const resize = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    };
    resize();
    window.addEventListener("resize", resize);

    const groundY = canvas.height * 0.78;
    const buildings = generateBuildings(canvas.width, groundY);

    // Stars
    const stars = Array.from({ length: 120 }, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * groundY * 0.6,
      r: Math.random() * 1.5,
      a: Math.random(),
      da: 0.005 + Math.random() * 0.01,
    }));

    // Window flicker state
    const flickerState: Record<string, boolean> = {};

    function draw(tick: number) {
      if (!ctx || !canvas) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Sky gradient
      const skyGrad = ctx.createLinearGradient(0, 0, 0, groundY);
      skyGrad.addColorStop(0, "#010408");
      skyGrad.addColorStop(0.6, "#020818");
      skyGrad.addColorStop(1, "#0a0f1e");
      ctx.fillStyle = skyGrad;
      ctx.fillRect(0, 0, canvas.width, groundY);

      // Stars
      stars.forEach((s) => {
        s.a += s.da;
        if (s.a > 1 || s.a < 0) s.da *= -1;
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255,255,255,${s.a * 0.8})`;
        ctx.fill();
      });

      // Moon
      ctx.beginPath();
      ctx.arc(canvas.width * 0.82, 60, 22, 0, Math.PI * 2);
      ctx.fillStyle = "#ffd70022";
      ctx.fill();
      ctx.beginPath();
      ctx.arc(canvas.width * 0.82, 60, 16, 0, Math.PI * 2);
      ctx.fillStyle = "#ffd70066";
      ctx.fill();

      // Distant glow behind skyline
      const glowGrad = ctx.createRadialGradient(
        canvas.width * 0.5, groundY, 0,
        canvas.width * 0.5, groundY, canvas.width * 0.6
      );
      glowGrad.addColorStop(0, "rgba(0,245,255,0.06)");
      glowGrad.addColorStop(1, "transparent");
      ctx.fillStyle = glowGrad;
      ctx.fillRect(0, 0, canvas.width, groundY);

      // Buildings (back layer, slightly desaturated)
      buildings.forEach((b) => {
        // Building body
        ctx.fillStyle = b.color;
        ctx.fillRect(b.x, groundY - b.h, b.w, b.h);

        // Edge highlight
        ctx.strokeStyle = "rgba(0,245,255,0.08)";
        ctx.lineWidth = 1;
        ctx.strokeRect(b.x, groundY - b.h, b.w, b.h);

        // Antenna
        if (b.hasAntenna) {
          ctx.strokeStyle = "rgba(0,245,255,0.4)";
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(b.x + b.w / 2, groundY - b.h);
          ctx.lineTo(b.x + b.w / 2, groundY - b.h - 18);
          ctx.stroke();
          // Blinking light
          if (active && Math.sin(tick * 0.05 + b.x) > 0.3) {
            ctx.beginPath();
            ctx.arc(b.x + b.w / 2, groundY - b.h - 18, 2.5, 0, Math.PI * 2);
            ctx.fillStyle = "#ff3333";
            ctx.fill();
          }
        }

        // Windows
        b.windows.forEach((w, wi) => {
          const key = `${b.x}-${wi}`;
          if (!flickerState[key]) flickerState[key] = Math.random() > 0.3;
          if (active && Math.random() < 0.001) flickerState[key] = !flickerState[key];
          if (!flickerState[key]) return;
          ctx.fillStyle = w.color + "99";
          ctx.fillRect(w.x, w.y, w.w, w.h);
          // Window glow
          ctx.shadowColor = w.color;
          ctx.shadowBlur = 4;
          ctx.fillStyle = w.color + "55";
          ctx.fillRect(w.x - 1, w.y - 1, w.w + 2, w.h + 2);
          ctx.shadowBlur = 0;
        });
      });

      // Ground
      const groundGrad = ctx.createLinearGradient(0, groundY, 0, canvas.height);
      groundGrad.addColorStop(0, "#0a0f1e");
      groundGrad.addColorStop(1, "#030712");
      ctx.fillStyle = groundGrad;
      ctx.fillRect(0, groundY, canvas.width, canvas.height - groundY);

      // Ground line neon
      ctx.strokeStyle = active ? "#00f5ff44" : "#00f5ff22";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, groundY);
      ctx.lineTo(canvas.width, groundY);
      ctx.stroke();

      // Road markings
      ctx.strokeStyle = "rgba(255,215,0,0.15)";
      ctx.lineWidth = 2;
      ctx.setLineDash([20, 30]);
      ctx.beginPath();
      ctx.moveTo(0, groundY + (canvas.height - groundY) * 0.5);
      ctx.lineTo(canvas.width, groundY + (canvas.height - groundY) * 0.5);
      ctx.stroke();
      ctx.setLineDash([]);

      // Animated neon sign on one building
      const signTick = Math.floor(tick / 30) % 3;
      const signX = canvas.width * 0.25;
      const signBuild = buildings.find((b) => b.x > signX) || buildings[2];
      if (signBuild) {
        const sy = groundY - signBuild.h * 0.4;
        const colors = ["#00f5ff", "#bf00ff", "#ffd700"];
        ctx.font = "bold 10px 'JetBrains Mono', monospace";
        ctx.fillStyle = colors[signTick];
        ctx.shadowColor = colors[signTick];
        ctx.shadowBlur = 8;
        ctx.fillText("LIVE", signBuild.x + 4, sy);
        ctx.shadowBlur = 0;
      }
    }

    const animate = () => {
      tickRef.current++;
      draw(tickRef.current);
      frameRef.current = requestAnimationFrame(animate);
    };

    frameRef.current = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(frameRef.current);
      window.removeEventListener("resize", resize);
    };
  }, [active]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full"
      style={{ display: "block" }}
    />
  );
}
