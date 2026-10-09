"use client";

import React, { useState } from "react";
import type { MarketDay } from "@/lib/types/api";
import { formatPrice, formatNumber } from "@/lib/format";
import { TrendingUp, Calendar, Home, ArrowUpRight } from "lucide-react";

interface MarketTrendChartProps {
  days: MarketDay[];
  className?: string;
  districtName?: string;
}

export const MarketTrendChart: React.FC<MarketTrendChartProps> = ({
  days,
  className = "",
  districtName = "khu vực",
}) => {
  if (!days || days.length === 0) {
    return (
      <div className={`p-8 rounded-2xl border border-[#E7E2DA] dark:border-slate-800 bg-[#FAF8F5] dark:bg-slate-900/60 text-center ${className}`}>
        <Calendar className="w-8 h-8 text-[#6B7280]/50 mx-auto mb-2" />
        <p className="text-sm text-[#6B7280]">Chưa có đủ chuỗi dữ liệu theo ngày cho {districtName}.</p>
      </div>
    );
  }

  // Filter days from 2026-09-23 onwards as specified in brief
  const filteredDays = days.filter((d) => d.date >= "2026-09-23");
  const chartDays = filteredDays.length > 0 ? filteredDays : days;

  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  const width = 1200;
  const height = 240;
  const padding = { top: 25, right: 60, bottom: 45, left: 60 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  const validPrices = chartDays
    .map((d) => d.median_price)
    .filter((p): p is number => p !== null && p > 0);

  const minPrice = validPrices.length > 0 ? Math.min(...validPrices) * 0.92 : 3_000_000;
  const maxPrice = validPrices.length > 0 ? Math.max(...validPrices) * 1.08 : 6_000_000;
  const priceRange = maxPrice - minPrice || 1;

  const maxNewListings = Math.max(...chartDays.map((d) => d.new_listings), 10) * 1.25;

  const barCount = chartDays.length;
  const stepX = chartW / Math.max(barCount, 1);
  const barWidth = Math.max(Math.min(stepX * 0.45, 28), 8);

  const getX = (idx: number) => padding.left + (idx + 0.5) * stepX;
  const getPriceY = (price: number) => padding.top + chartH - ((price - minPrice) / priceRange) * chartH;
  const getListingY = (count: number) => padding.top + chartH - (count / maxNewListings) * chartH;

  // Compute curved SVG path
  const points: { x: number; y: number; price: number; date: string; newListings: number }[] = [];
  chartDays.forEach((d, idx) => {
    if (d.median_price !== null && d.median_price > 0) {
      points.push({
        x: getX(idx),
        y: getPriceY(d.median_price),
        price: d.median_price,
        date: d.date,
        newListings: d.new_listings,
      });
    }
  });

  let curvePathD = "";
  if (points.length > 0) {
    curvePathD = `M ${points[0].x} ${points[0].y}`;
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[i];
      const p1 = points[i + 1];
      const cpx = (p0.x + p1.x) / 2;
      curvePathD += ` C ${cpx} ${p0.y}, ${cpx} ${p1.y}, ${p1.x} ${p1.y}`;
    }
  }

  let areaCurveD = "";
  if (points.length > 1) {
    const bottomY = padding.top + chartH;
    areaCurveD = `${curvePathD} L ${points[points.length - 1].x} ${bottomY} L ${points[0].x} ${bottomY} Z`;
  }

  const latestDay = chartDays[chartDays.length - 1];
  const latestDayLabel = latestDay
    ? `ngày ${latestDay.date.slice(8, 10)}/${latestDay.date.slice(5, 7)}`
    : "gần nhất";

  return (
    <div className={`space-y-6 ${className}`}>
      {/* Top Section Header & Stat Pills */}
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 pb-2">
        <div className="space-y-1.5 max-w-xl">
          <span className="text-[#B8892E] text-[11px] font-semibold uppercase tracking-widest block">
            Chuỗi theo ngày
          </span>
          <h2 className="font-display text-2xl sm:text-3xl font-medium text-[#111827] dark:text-white tracking-tight">
            Xu hướng giá theo ngày ({districtName})
          </h2>
          <p className="text-xs sm:text-sm text-[#6B7280] dark:text-slate-400 font-sans">
            Giá trung vị các tin cho thuê ghi nhận mỗi ngày (bỏ hai ngày cào đầu tiên 20–22/09).
          </p>
        </div>

        {/* 3 Metric Pills */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="px-4 py-2.5 rounded-2xl bg-white dark:bg-[#1A2234] border border-[#E7E2DA] dark:border-slate-800 shadow-xs flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-[#0F5F58]/10 text-[#0F5F58] flex items-center justify-center shrink-0">
              <TrendingUp className="w-4 h-4" />
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-[#6B7280] font-semibold">
                Trung vị {latestDayLabel}
              </div>
              <div className="text-sm font-bold text-[#0F5F58] dark:text-[#91D6CD]">
                {formatPrice(latestDay?.median_price, { shortUnit: true })}
              </div>
            </div>
          </div>

          <div className="px-4 py-2.5 rounded-2xl bg-white dark:bg-[#1A2234] border border-[#E7E2DA] dark:border-slate-800 shadow-xs flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-[#B8892E]/15 text-[#B8892E] flex items-center justify-center shrink-0">
              <Home className="w-4 h-4" />
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-[#6B7280] font-semibold">
                Tin mới {latestDayLabel}
              </div>
              <div className="text-sm font-bold text-[#111827] dark:text-white">
                {latestDay ? `${latestDay.new_listings} tin` : "—"}
              </div>
            </div>
          </div>

        </div>
      </div>

      {/* Vector Chart Canvas */}
      <div className="bg-white dark:bg-[#1A2234] rounded-3xl p-6 sm:p-8 border border-[#E7E2DA] dark:border-slate-800 shadow-sm relative overflow-hidden">
        {/* Legend */}
        <div className="flex flex-wrap items-center justify-between pb-6 mb-2 border-b border-[#E7E2DA]/60 dark:border-slate-800 gap-4">
          <div className="flex items-center gap-6 text-xs font-semibold">
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-[#0F5F58]" />
              <span className="text-[#111827] dark:text-white">Đường giá trung vị (triệu ₫)</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-md bg-[#FCC665]" />
              <span className="text-[#6B7280] dark:text-slate-400">Số tin niêm yết mới hàng ngày</span>
            </div>
          </div>
          <div className="text-[11px] text-[#9CA3AF]">Nguồn: tin đăng RoomBeacon ghi nhận mỗi ngày</div>
        </div>

        {/* SVG Canvas */}
        <div className="w-full overflow-x-auto">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full h-auto min-w-[680px] select-none overflow-visible"
          >
            <defs>
              <linearGradient id="areaGradientTrend" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#0F5F58" stopOpacity="0.22" />
                <stop offset="100%" stopColor="#0F5F58" stopOpacity="0.0" />
              </linearGradient>
            </defs>

            {/* Horizontal Grid Guides */}
            {[0, 0.33, 0.66, 1].map((pct, i) => {
              const val = minPrice + priceRange * (1 - pct);
              const y = padding.top + chartH * pct;
              return (
                <g key={i}>
                  <line
                    x1={padding.left}
                    x2={width - padding.right}
                    y1={y}
                    y2={y}
                    stroke="#E7E2DA"
                    strokeDasharray="4 4"
                    strokeWidth="1"
                    opacity="0.8"
                  />
                  <text
                    x={padding.left - 10}
                    y={y + 4}
                    fill="#6B7280"
                    fontSize="11"
                    fontFamily="Be Vietnam Pro"
                    textAnchor="end"
                  >
                    {formatPrice(val, { shortUnit: true })}
                  </text>
                </g>
              );
            })}

            {/* Histogram Bars (Champagne Gold / Secondary) */}
            {chartDays.map((d, idx) => {
              const x = getX(idx) - barWidth / 2;
              const barH = ((d.new_listings || 0) / maxNewListings) * chartH;
              const y = padding.top + chartH - barH;
              const isHovered = hoveredIdx === idx;

              return (
                <g key={d.date} onMouseEnter={() => setHoveredIdx(idx)} onMouseLeave={() => setHoveredIdx(null)}>
                  <rect
                    x={x}
                    y={y}
                    width={barWidth}
                    height={barH}
                    rx="4"
                    fill="#FCC665"
                    opacity={isHovered ? 0.95 : 0.45}
                    className="transition-all cursor-pointer"
                  />
                </g>
              );
            })}

            {/* Smooth Curved Area Fill */}
            {areaCurveD && (
              <path d={areaCurveD} fill="url(#areaGradientTrend)" pointerEvents="none" />
            )}

            {/* Primary Smooth Trend Curve (Deep Teal) */}
            {curvePathD && (
              <path
                d={curvePathD}
                fill="none"
                stroke="#0F5F58"
                strokeWidth="3"
                strokeLinecap="round"
                pointerEvents="none"
              />
            )}

            {/* Data Point Markers */}
            {points.map((p, idx) => {
              const isHovered = hoveredIdx === idx;
              return (
                <g key={idx} onMouseEnter={() => setHoveredIdx(idx)} onMouseLeave={() => setHoveredIdx(null)}>
                  <circle
                    cx={p.x}
                    cy={p.y}
                    r={isHovered ? 6 : 4.5}
                    fill="#0F5F58"
                    stroke="#FFFFFF"
                    strokeWidth="2"
                    className="cursor-pointer transition-all"
                  />
                  {isHovered && (
                    <g pointerEvents="none">
                      <rect
                        x={p.x - 45}
                        y={p.y - 36}
                        width="90"
                        height="26"
                        rx="6"
                        fill="#111827"
                        className="shadow-md"
                      />
                      <text
                        x={p.x}
                        y={p.y - 19}
                        fill="#FFFFFF"
                        fontSize="11"
                        fontWeight="600"
                        fontFamily="Be Vietnam Pro"
                        textAnchor="middle"
                      >
                        {formatPrice(p.price, { shortUnit: true })} ({p.newListings} tin)
                      </text>
                    </g>
                  )}
                </g>
              );
            })}

            {/* X-axis date labels */}
            {chartDays.map((d, idx) => {
              if (idx % Math.ceil(chartDays.length / 7) === 0 || idx === chartDays.length - 1) {
                const x = getX(idx);
                const dayLabel = d.date.slice(5).replace("-", "/");
                return (
                  <text
                    key={d.date}
                    x={x}
                    y={padding.top + chartH + 24}
                    fill="#6B7280"
                    fontSize="11"
                    fontFamily="Be Vietnam Pro"
                    textAnchor="middle"
                  >
                    {dayLabel}
                  </text>
                );
              }
              return null;
            })}
          </svg>
        </div>
      </div>
    </div>
  );
};
