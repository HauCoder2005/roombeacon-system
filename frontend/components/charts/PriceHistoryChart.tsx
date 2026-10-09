"use client";

import React from "react";
import type { PricePoint } from "@/lib/types/api";
import { formatPrice, formatVietnamDateTime } from "@/lib/format";
import { History, Minus, TrendingDown, TrendingUp } from "lucide-react";

interface PriceHistoryChartProps {
  points: PricePoint[];
  className?: string;
}

type Step = { start: number; end: number; price: number; scans: number };

/** Collapses consecutive scans with the same price into one step. */
function toSteps(points: PricePoint[]): Step[] {
  const valid = points
    .filter((p) => p.price !== null && p.price > 0)
    .map((p) => ({ t: new Date(p.observed_at).getTime(), price: p.price as number }))
    .filter((p) => Number.isFinite(p.t))
    .sort((a, b) => a.t - b.t);
  const steps: Step[] = [];
  for (const p of valid) {
    const last = steps[steps.length - 1];
    if (last && last.price === p.price) {
      last.end = p.t;
      last.scans += 1;
    } else {
      steps.push({ start: p.t, end: p.t, price: p.price, scans: 1 });
    }
  }
  return steps;
}

const shortDate = (t: number) =>
  new Date(t).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", timeZone: "Asia/Ho_Chi_Minh" });

const MAX_LABELLED_STEPS = 6;

export const PriceHistoryChart: React.FC<PriceHistoryChartProps> = ({ points, className = "" }) => {
  const steps = toSteps(points ?? []);

  if (steps.length === 0) {
    return (
      <section className={`rounded-2xl border border-border bg-bg-alt p-6 text-center ${className}`}>
        <History className="mx-auto mb-2 h-8 w-8 text-ink-subtle" strokeWidth={1.4} aria-hidden />
        <p className="text-sm text-ink-muted">Chưa có lịch sử giá cho tin này.</p>
      </section>
    );
  }

  const first = steps[0];
  const last = steps[steps.length - 1];
  const diff = last.price - first.price;
  const diffPct = first.price > 0 ? (diff / first.price) * 100 : 0;
  const totalScans = steps.reduce((n, s) => n + s.scans, 0);

  const width = 700;
  const height = 170;
  const pad = { top: 28, right: 24, bottom: 16, left: 56 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;

  const prices = steps.map((s) => s.price);
  const lo = Math.min(...prices);
  const hi = Math.max(...prices);
  const span = hi - lo;
  const minPrice = span ? lo - span * 0.15 : lo * 0.9;
  const maxPrice = span ? hi + span * 0.15 : lo * 1.1;
  const priceRange = maxPrice - minPrice || 1;

  const t0 = first.start;
  const t1 = Math.max(last.end, last.start);
  const timeRange = t1 - t0;
  const x = (t: number) => (timeRange ? pad.left + ((t - t0) / timeRange) * chartW : pad.left + chartW / 2);
  const y = (v: number) => pad.top + chartH - ((v - minPrice) / priceRange) * chartH;

  let d = "";
  steps.forEach((s, i) => {
    const sx = timeRange ? x(s.start) : pad.left;
    const ex = timeRange ? x(i < steps.length - 1 ? steps[i + 1].start : s.end) : width - pad.right;
    d += i === 0 ? `M ${sx} ${y(s.price)}` : ` L ${sx} ${y(s.price)}`;
    d += ` L ${ex} ${y(s.price)}`;
  });

  // Label only price changes; when there are many, keep the first, last and largest moves.
  const labelled = new Set<number>([0, steps.length - 1]);
  if (steps.length > MAX_LABELLED_STEPS) {
    steps
      .map((s, i) => ({ i, move: i ? Math.abs(s.price - steps[i - 1].price) : 0 }))
      .sort((a, b) => b.move - a.move)
      .slice(0, MAX_LABELLED_STEPS - 2)
      .forEach(({ i }) => labelled.add(i));
  } else {
    steps.forEach((_, i) => labelled.add(i));
  }

  return (
    <section className={`flex flex-col gap-5 rounded-2xl border border-border bg-surface p-6 md:p-8 ${className}`}>
      <header className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div>
          <h2 className="flex items-center gap-2 font-display text-xl font-medium text-ink">
            <History className="h-5 w-5 text-brand" strokeWidth={1.6} aria-hidden />
            Lịch sử giá niêm yết
          </h2>
          <p className="mt-0.5 text-xs text-ink-muted">
            {totalScans} lần ghi nhận · {steps.length === 1 ? "chưa đổi giá" : `${steps.length - 1} lần đổi giá`}
          </p>
        </div>
        {diff !== 0 ? (
          <span
            className={`inline-flex items-center gap-1.5 self-start rounded-full px-3 py-1.5 text-xs font-semibold ${
              diff < 0 ? "bg-good-soft text-good" : "bg-bad-soft text-bad"
            }`}
          >
            {diff < 0 ? <TrendingDown className="h-4 w-4" aria-hidden /> : <TrendingUp className="h-4 w-4" aria-hidden />}
            {diff < 0 ? "Giảm" : "Tăng"} {formatPrice(Math.abs(diff), { shortUnit: true })} ({diffPct > 0 ? "+" : ""}
            {diffPct.toFixed(1)}%)
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 self-start rounded-full border border-border bg-bg-alt px-3 py-1.5 text-xs font-medium text-ink-soft">
            <Minus className="h-3.5 w-3.5" aria-hidden />
            Giá không đổi
          </span>
        )}
      </header>

      <div className="rounded-xl border border-border-subtle bg-bg-alt p-4">
        <svg
          className="h-44 w-full overflow-visible"
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          role="img"
          aria-label={`Giá từ ${formatPrice(first.price)} đến ${formatPrice(last.price)}`}
        >
          {[0, 0.5, 1].map((f) => (
            <g key={f}>
              <line
                x1={pad.left}
                x2={width - pad.right}
                y1={pad.top + chartH * f}
                y2={pad.top + chartH * f}
                stroke="var(--border)"
                strokeDasharray="4 4"
              />
              <text
                x={pad.left - 10}
                y={pad.top + chartH * f + 4}
                fill="var(--muted)"
                fontSize="11"
                textAnchor="end"
              >
                {formatPrice(maxPrice - priceRange * f, { shortUnit: true })}
              </text>
            </g>
          ))}
          <path d={d} fill="none" stroke="var(--brand)" strokeWidth="2.5" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
          {steps.map((s, i) => {
            const cx = timeRange ? x(s.start) : pad.left + chartW / 2;
            const isLast = i === steps.length - 1;
            return (
              <g key={s.start}>
                <circle cx={cx} cy={y(s.price)} r={isLast ? 5.5 : 4.5} fill={isLast ? "var(--brand)" : "var(--surface)"} stroke="var(--brand)" strokeWidth="2" />
                {labelled.has(i) && (
                  <text x={cx} y={y(s.price) - 11} fill="var(--ink)" fontSize="12" fontWeight="600" textAnchor={i === 0 && steps.length > 1 ? "start" : isLast && steps.length > 1 ? "end" : "middle"}>
                    {formatPrice(s.price, { shortUnit: true })}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
        <div className="mt-2 flex justify-between border-t border-border-subtle pt-2 text-xs text-ink-muted">
          <span>
            <span className="block font-semibold text-ink">{shortDate(t0)}</span>
            Lần đầu ghi nhận
          </span>
          <span className="text-right">
            <span className="block font-semibold text-brand">{shortDate(t1)}</span>
            Gần nhất
          </span>
        </div>
      </div>

      <p className="text-[12px] text-ink-muted">
        Cập nhật gần nhất {formatVietnamDateTime(new Date(t1).toISOString())}. Mỗi bậc là một mức giá RoomBeacon ghi nhận trên tin đăng gốc.
      </p>
    </section>
  );
};
