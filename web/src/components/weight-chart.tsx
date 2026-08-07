"use client";

import { useMemo, useRef, useState } from "react";

import { shortDate } from "@/lib/format";

/** The weight trend as the sheet draws it: raw weigh-ins as quiet ink dots,
 * the 7-day smoothed trend as the one honey line — the same reservation the
 * rest of the sheet makes, ochre for the number that is alive today. Axes
 * recede to hairlines; a finger or pointer on the plot reads out a single
 * day in the price-column voice. */

type Point = { date: string; weight_kg: number | null };
type Smoothed = { date: string; weight_kg: number };

const W = 360;
const H = 168;
const M = { top: 10, right: 8, bottom: 20, left: 34 };

function dayIndex(dateISO: string): number {
  return Math.round(new Date(`${dateISO}T00:00:00Z`).getTime() / 86_400_000);
}

export function WeightChart({
  points,
  smoothed,
  locale,
  ariaLabel,
}: {
  points: Point[];
  smoothed: Smoothed[];
  locale: string;
  ariaLabel: string;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null); // index into `weighed`

  const weighed = useMemo(
    () => points.filter((p): p is { date: string; weight_kg: number } => p.weight_kg != null),
    [points],
  );

  const geometry = useMemo(() => {
    if (weighed.length === 0) return null;
    const xs = weighed.map((p) => dayIndex(p.date));
    const x0 = Math.min(...xs);
    const x1 = Math.max(...xs);
    const values = weighed.map((p) => p.weight_kg).concat(smoothed.map((s) => s.weight_kg));
    const lo = Math.min(...values);
    const hi = Math.max(...values);
    const pad = Math.max(0.3, (hi - lo) * 0.12);
    const y0 = lo - pad;
    const y1 = hi + pad;
    const x = (dateISO: string) =>
      x1 === x0
        ? (M.left + W - M.right) / 2
        : M.left + ((dayIndex(dateISO) - x0) / (x1 - x0)) * (W - M.left - M.right);
    const y = (kg: number) => M.top + ((y1 - kg) / (y1 - y0)) * (H - M.top - M.bottom);
    // Three hairline ticks across the range, printed to one decimal.
    const ticks = [y0 + (y1 - y0) * 0.15, (y0 + y1) / 2, y0 + (y1 - y0) * 0.85].map(
      (v) => Math.round(v * 10) / 10,
    );
    return { x, y, ticks, x0, x1 };
  }, [weighed, smoothed]);

  if (!geometry || weighed.length === 0) return null;

  const { x, y, ticks } = geometry;
  const nf = new Intl.NumberFormat(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 });

  const trendPath = smoothed
    .map((s, i) => `${i === 0 ? "M" : "L"}${x(s.date).toFixed(1)},${y(s.weight_kg).toFixed(1)}`)
    .join("");

  const smoothedByDate = new Map(smoothed.map((s) => [s.date, s.weight_kg]));
  const hovered = hover != null ? weighed[hover] : null;
  const hoveredTrend = hovered ? smoothedByDate.get(hovered.date) : undefined;

  function locate(clientX: number) {
    const svg = svgRef.current;
    if (!svg || weighed.length === 0) return;
    const rect = svg.getBoundingClientRect();
    const vx = ((clientX - rect.left) / rect.width) * W;
    let nearest = 0;
    let best = Infinity;
    weighed.forEach((p, i) => {
      const d = Math.abs(x(p.date) - vx);
      if (d < best) {
        best = d;
        nearest = i;
      }
    });
    setHover(nearest);
  }

  // The readout sits above the plot; near the edges it anchors from the
  // other side so the figures never fall off the sheet.
  const readoutX = hovered ? x(hovered.date) : 0;
  const readoutAnchor = readoutX < 96 ? "start" : readoutX > W - 96 ? "end" : "middle";

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${W} ${H}`}
      className="w-full touch-pan-y"
      role="img"
      aria-label={ariaLabel}
      onPointerMove={(e) => locate(e.clientX)}
      onPointerDown={(e) => locate(e.clientX)}
      onPointerLeave={() => setHover(null)}
    >
      {/* Recessive scale: three hairlines, kg figures in the margin */}
      {ticks.map((tick) => (
        <g key={tick}>
          <line
            x1={M.left}
            x2={W - M.right}
            y1={y(tick)}
            y2={y(tick)}
            stroke="var(--border)"
            strokeWidth="1"
          />
          <text
            x={M.left - 5}
            y={y(tick) + 3}
            textAnchor="end"
            fontSize="9"
            fill="var(--muted-foreground)"
            className="font-mono tnum"
          >
            {nf.format(tick)}
          </text>
        </g>
      ))}

      {/* The window's edges, dated */}
      <text
        x={M.left}
        y={H - 6}
        fontSize="9"
        fill="var(--muted-foreground)"
        className="font-mono tnum"
      >
        {shortDate(weighed[0].date, locale)}
      </text>
      {weighed.length > 1 && (
        <text
          x={W - M.right}
          y={H - 6}
          textAnchor="end"
          fontSize="9"
          fill="var(--muted-foreground)"
          className="font-mono tnum"
        >
          {shortDate(weighed[weighed.length - 1].date, locale)}
        </text>
      )}

      {/* Raw weigh-ins: the mornings as they were said */}
      {weighed.map((p) => (
        <circle
          key={p.date}
          cx={x(p.date)}
          cy={y(p.weight_kg)}
          r="2.4"
          fill="var(--muted-foreground)"
          opacity="0.55"
        />
      ))}

      {/* The smoothed trend: the number that matters, in the action color */}
      {smoothed.length > 1 && (
        <path
          d={trendPath}
          fill="none"
          stroke="var(--primary)"
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      )}

      {/* One day under the finger: crosshair, marked morning, mono readout */}
      {hovered && (
        <g pointerEvents="none">
          <line
            x1={x(hovered.date)}
            x2={x(hovered.date)}
            y1={M.top}
            y2={H - M.bottom}
            stroke="var(--foreground)"
            strokeWidth="1"
            opacity="0.35"
          />
          <circle
            cx={x(hovered.date)}
            cy={y(hovered.weight_kg)}
            r="3.5"
            fill="var(--background)"
            stroke="var(--foreground)"
            strokeWidth="1.5"
          />
          <text
            x={readoutX}
            y={M.top - 1}
            textAnchor={readoutAnchor}
            fontSize="10"
            fill="var(--foreground)"
            className="font-mono tnum"
          >
            {shortDate(hovered.date, locale)} · {nf.format(hovered.weight_kg)}
            {hoveredTrend != null && hoveredTrend !== hovered.weight_kg
              ? ` (${nf.format(hoveredTrend)})`
              : ""}
            {" kg"}
          </text>
        </g>
      )}
    </svg>
  );
}
