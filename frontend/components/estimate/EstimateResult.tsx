"use client";

import React from "react";
import Link from "next/link";
import type { PriceEstimate } from "@/lib/types/api";
import { formatPrice, formatWarning, formatArea } from "@/lib/format";
import {
  AlertTriangle,
  Sparkles,
  ArrowRight,
  HelpCircle,
  TrendingDown,
  TrendingUp,
  Calendar,
  Layers,
} from "lucide-react";

interface EstimateResultProps {
  estimate: PriceEstimate;
  districtId: string;
  wardId?: string;
  onOpenModelCard: () => void;
}

export const EstimateResult: React.FC<EstimateResultProps> = ({
  estimate,
  districtId,
  wardId,
  onOpenModelCard,
}) => {
  const { range, inputs_used, market, warnings, disclaimer } = estimate;

  const searchUrl = `/tim-phong?district_id=${districtId}${
    wardId ? `&ward_id=${wardId}` : ""
  }&price_min=${range.low}&price_max=${range.high}`;

  const medianPrice = market.median || (range.low + range.high) / 2;
  const deltaPct = medianPrice > 0 ? ((estimate.estimate - medianPrice) / medianPrice) * 100 : 0;
  const isCheaper = deltaPct < 0;

  const scaleMin = range.low * 0.85;
  const scaleMax = range.high * 1.25;
  const scaleSpan = scaleMax - scaleMin || 1;

  const getPositionPercent = (val: number) => {
    const pct = ((val - scaleMin) / scaleSpan) * 100;
    return Math.max(5, Math.min(95, pct));
  };

  const calculatedPct = getPositionPercent(estimate.estimate);
  const medianPct = getPositionPercent(medianPrice);
  const p25Pct = getPositionPercent(market.p25 || range.low);
  const p75Pct = getPositionPercent(market.p75 || range.high);

  return (
    <div className="bg-[#FAF8F5] dark:bg-slate-900/90 rounded-[24px] p-7 sm:p-9 border border-[#E7E2DA] dark:border-slate-800 shadow-sm relative overflow-hidden space-y-6">
      {/* Top Header & Model Status Badge */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#E7E2DA] dark:border-slate-800 pb-5">
        <div className="flex items-center gap-2.5">
          <span className="text-[11px] uppercase tracking-widest text-[#6B7280] dark:text-slate-400 font-bold">
            Giá thuê ước tính mô hình
          </span>
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-[#0F5F58]/10 text-[#0F5F58] dark:text-[#91D6CD]">
            Thử nghiệm · {estimate.model.model_id}
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs text-[#6B7280]">
          <button
            type="button"
            onClick={onOpenModelCard}
            className="text-xs text-[#0F5F58] dark:text-[#91D6CD] hover:underline flex items-center gap-1 font-semibold cursor-pointer"
          >
            <HelpCircle className="w-3.5 h-3.5" />
            <span>Về mô hình</span>
          </button>
        </div>
      </div>

      {/* Hero Estimated Price Segment */}
      <div className="py-4 border-b border-[#E7E2DA] dark:border-slate-800">
        <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-3">
          <div>
            <div className="font-display text-4xl sm:text-5xl font-medium text-[#0F5F58] dark:text-[#91D6CD] tracking-tight">
              {formatPrice(range.low, { shortUnit: true })} – {formatPrice(range.high, { shortUnit: true })}
              <span className="text-base sm:text-lg text-[#6B7280] dark:text-slate-400 font-sans font-normal ml-2">
                / tháng
              </span>
            </div>
          </div>
          <div className="text-left sm:text-right">
            <div className="text-xs font-semibold text-[#111827] dark:text-white">
              Điểm giữa ước tính: {formatPrice(estimate.estimate, { shortUnit: true })}
            </div>
            <div className="text-[11px] text-[#6B7280] mt-0.5">
              Tương đương ~{Math.round(estimate.estimate / inputs_used.area_m2).toLocaleString("vi-VN")} ₫/m²
            </div>
          </div>
        </div>
      </div>

      {/* Signature Market Intelligence Component: "Dải Giá Thị Trường" */}
      <div className="py-2 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="space-y-0.5">
            <div className="text-xs font-semibold text-[#111827] dark:text-white flex items-center gap-2">
              <span>Thị trường {market.name}</span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-white dark:bg-slate-800 border border-[#E7E2DA] dark:border-slate-700 text-[#6B7280]">
                Phân khúc phòng {inputs_used.area_m2}m²
              </span>
            </div>
            <div className="text-xs text-[#6B7280]">
              Trung vị khu vực: <strong className="text-[#111827] dark:text-white font-semibold">{formatPrice(medianPrice, { shortUnit: true })}</strong> (P50)
            </div>
          </div>

          <div
            className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold self-start sm:self-auto ${
              isCheaper
                ? "bg-[#ECFDF5] text-[#047857]"
                : "bg-[#FEF2F2] text-[#B91C1C]"
            }`}
          >
            {isCheaper ? (
              <TrendingDown className="w-3.5 h-3.5" />
            ) : (
              <TrendingUp className="w-3.5 h-3.5" />
            )}
            <span>
              {isCheaper ? "Thấp hơn" : "Cao hơn"} {Math.abs(deltaPct).toFixed(1)}% so với trung vị
            </span>
          </div>
        </div>

        {/* Graphic Price Strip with markers */}
        <div className="pt-8 pb-3">
          <div className="relative w-full h-8 flex items-center">
            {/* Continuous Track */}
            <div className="w-full h-2.5 bg-[#E7E2DA] dark:bg-slate-700 rounded-full relative overflow-hidden">
              {/* IQR highlight */}
              <div
                className="absolute top-0 bottom-0 bg-[#0F5F58]/25 rounded-full"
                style={{
                  left: `${Math.min(p25Pct, p75Pct)}%`,
                  width: `${Math.abs(p75Pct - p25Pct)}%`,
                }}
              />
            </div>

            {/* Marker 1: Calculated Price Point */}
            <div
              className="absolute -top-7 -translate-x-1/2 flex flex-col items-center z-10"
              style={{ left: `${calculatedPct}%` }}
            >
              <div className="bg-[#0F5F58] text-white text-[10px] font-bold px-2 py-0.5 rounded shadow-sm whitespace-nowrap mb-1">
                Ước tính: {formatPrice(estimate.estimate, { shortUnit: true })}
              </div>
              <div className="w-4 h-4 rounded-full bg-[#0F5F58] border-2 border-white shadow-md ring-2 ring-[#0F5F58]/30" />
            </div>

            {/* Marker 2: Neighborhood Median */}
            <div
              className="absolute top-5 -translate-x-1/2 flex flex-col items-center"
              style={{ left: `${medianPct}%` }}
            >
              <div className="w-3.5 h-3.5 rounded-full bg-[#B8892E] border-2 border-white shadow-xs" />
              <div className="text-[10px] font-semibold text-[#B8892E] whitespace-nowrap mt-1">
                Trung vị: {formatPrice(medianPrice, { shortUnit: true })}
              </div>
            </div>
          </div>

          {/* Range Legend */}
          <div className="flex justify-between gap-2 items-center text-[10px] text-[#6B7280] dark:text-slate-400 mt-6 px-1">
            <span className="font-semibold text-[#111827] dark:text-white">
              P25: {formatPrice(market.p25 || range.low, { shortUnit: true })} (thị trường)
            </span>
            <span className="font-semibold text-[#111827] dark:text-white">
              P75: {formatPrice(market.p75 || range.high, { shortUnit: true })} (thị trường)
            </span>
          </div>
        </div>
      </div>

      {/* Warnings / Outlier Domain Callout */}
      {warnings && warnings.length > 0 && (
        <div className="p-4 rounded-xl bg-[#FEF3C7] dark:bg-amber-950/40 border border-[#FDE68A] dark:border-amber-800 text-[#92400E] dark:text-amber-200 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 shrink-0 text-[#B45309] dark:text-amber-400 mt-0.5" />
          <div className="space-y-1 text-xs">
            <div className="font-bold tracking-tight">
              Lưu ý về độ tin cậy:
            </div>
            {warnings.map((w, idx) => (
              <p key={idx} className="leading-relaxed">
                {formatWarning(w)}
              </p>
            ))}
          </div>
        </div>
      )}

      {/* Key Statistical Reliability Metrics (3-Column Bento) */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
        <div className="bg-white dark:bg-[#1A2234] p-3.5 rounded-xl border border-[#E7E2DA] dark:border-slate-800">
          <div className="text-[10px] uppercase tracking-wider text-[#6B7280] font-semibold">
            Độ phủ khoảng giá
          </div>
          <div className="font-display text-xl font-bold text-[#111827] dark:text-white mt-1">
            {Math.round(range.coverage * 100)}%
          </div>
          <div className="text-[10px] text-[#6B7280] mt-0.5">Tỷ lệ giá thật nằm trong khoảng (tập kiểm thử)</div>
        </div>
        <div className="bg-white dark:bg-[#1A2234] p-3.5 rounded-xl border border-[#E7E2DA] dark:border-slate-800">
          <div className="text-[10px] uppercase tracking-wider text-[#6B7280] font-semibold">
            Diện tích nhập
          </div>
          <div className="font-display text-xl font-bold text-[#111827] dark:text-white mt-1">
            {formatArea(inputs_used.area_m2)}
          </div>
          <div className="text-[10px] text-[#6B7280] mt-0.5">{inputs_used.ward ? `${inputs_used.ward}, ` : ""}{inputs_used.district}</div>
        </div>
        <div className="bg-white dark:bg-[#1A2234] p-3.5 rounded-xl border border-[#E7E2DA] dark:border-slate-800">
          <div className="text-[10px] uppercase tracking-wider text-[#6B7280] font-semibold">
            Tin có giá trong khu vực
          </div>
          <div className="font-display text-xl font-bold text-[#0F5F58] dark:text-[#91D6CD] mt-1">
            {market.listing_count} tin
          </div>
          <div className="text-[10px] text-[#6B7280] mt-0.5">Dùng để tính trung vị</div>
        </div>
      </div>

      {disclaimer && <p className="text-[11px] leading-relaxed text-ink-muted">{disclaimer}</p>}

      {/* CTA: Browse matching listings */}
      <div className="pt-2">
        <Link
          href={searchUrl}
          className="w-full py-3.5 px-6 rounded-full bg-[#0F5F58] hover:bg-[#004640] text-white font-semibold text-xs transition-all shadow-md flex items-center justify-center gap-2 cursor-pointer"
        >
          <span>Tìm các phòng thực tế trong tầm giá này</span>
          <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    </div>
  );
};
