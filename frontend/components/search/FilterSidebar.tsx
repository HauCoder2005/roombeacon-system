"use client";

import React from "react";
import { SlidersHorizontal, RotateCcw, ArrowUpDown } from "lucide-react";

interface FilterSidebarProps {
  priceMin?: number;
  priceMax?: number;
  areaMin?: number;
  areaMax?: number;
  sort?: string;
  onPriceChange: (min?: number, max?: number) => void;
  onAreaChange: (min?: number, max?: number) => void;
  onSortChange: (sort: string) => void;
  onReset: () => void;
  className?: string;
}

const PRICE_PRESETS = [
  { label: "Tất cả", min: undefined, max: undefined },
  { label: "Dưới 3 tr", min: undefined, max: 3000000 },
  { label: "3 – 5 tr", min: 3000000, max: 5000000 },
  { label: "5 – 8 tr", min: 5000000, max: 8000000 },
  { label: "8 – 12 tr", min: 8000000, max: 12000000 },
  { label: "> 12 tr", min: 12000000, max: undefined },
];

const AREA_PRESETS = [
  { label: "Tất cả", min: undefined, max: undefined },
  { label: "Dưới 20 m²", min: undefined, max: 20 },
  { label: "20 – 30 m²", min: 20, max: 30 },
  { label: "30 – 45 m²", min: 30, max: 45 },
  { label: "Trên 45 m²", min: 45, max: undefined },
];

const SORT_OPTIONS = [
  { label: "Mới quan sát nhất", value: "-last_observed_at" },
  { label: "Giá tăng dần", value: "price" },
  { label: "Giá giảm dần", value: "-price" },
  { label: "Diện tích tăng dần", value: "area" },
  { label: "Diện tích giảm dần", value: "-area" },
];

export const FilterSidebar: React.FC<FilterSidebarProps> = ({
  priceMin,
  priceMax,
  areaMin,
  areaMax,
  sort = "-last_observed_at",
  onPriceChange,
  onAreaChange,
  onSortChange,
  onReset,
  className = "",
}) => {
  return (
    <aside
      className={`bg-white dark:bg-[#1A2234] rounded-2xl p-6 shadow-sm border border-[#E7E2DA] dark:border-slate-800 space-y-6 ${className}`}
    >
      {/* Sidebar Header */}
      <div className="flex items-center justify-between pb-4 border-b border-[#E7E2DA] dark:border-slate-800">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="w-4 h-4 text-[#0F5F58] dark:text-[#91D6CD]" />
          <h3 className="font-display text-lg font-medium text-[#111827] dark:text-white">
            Bộ lọc tìm kiếm
          </h3>
        </div>
        <button
          type="button"
          onClick={onReset}
          className="text-xs text-[#B8892E] hover:underline font-semibold cursor-pointer"
        >
          Thiết lập lại
        </button>
      </div>

      {/* Sắp xếp */}
      <div className="space-y-2">
        <span className="text-[11px] uppercase tracking-wider text-[#6B7280] dark:text-slate-400 font-semibold block">
          Sắp xếp theo
        </span>
        <select
          value={sort}
          onChange={(e) => onSortChange(e.target.value)}
          className="w-full text-xs font-semibold bg-[#FAF8F5] dark:bg-slate-900 border border-[#E7E2DA] dark:border-slate-800 rounded-xl px-3 py-2.5 text-[#111827] dark:text-white outline-none focus:border-[#0F5F58]"
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Mức giá thuê */}
      <div className="space-y-3 pt-2 border-t border-[#E7E2DA] dark:border-slate-800">
        <div className="flex items-center justify-between">
          <span className="text-[11px] uppercase tracking-wider text-[#6B7280] dark:text-slate-400 font-semibold">
            Mức giá thuê
          </span>
          <span className="text-xs font-semibold text-[#B8892E]">
            {priceMin || priceMax
              ? `${priceMin ? priceMin / 1000000 : 0} – ${priceMax ? priceMax / 1000000 : "∞"} tr`
              : "Tất cả"}
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {PRICE_PRESETS.map((preset, idx) => {
            const isActive = priceMin === preset.min && priceMax === preset.max;
            return (
              <button
                key={idx}
                type="button"
                onClick={() => onPriceChange(preset.min, preset.max)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer ${
                  isActive
                    ? "bg-[#0F5F58] text-white shadow-xs font-semibold"
                    : "bg-[#FAF8F5] dark:bg-slate-900 text-[#4B5563] dark:text-slate-300 hover:bg-[#E7E2DA] dark:hover:bg-slate-800 border border-[#E7E2DA] dark:border-slate-800"
                }`}
              >
                {preset.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Diện tích không gian */}
      <div className="space-y-3 pt-2 border-t border-[#E7E2DA] dark:border-slate-800">
        <span className="text-[11px] uppercase tracking-wider text-[#6B7280] dark:text-slate-400 font-semibold block">
          Diện tích không gian
        </span>
        <div className="grid grid-cols-2 gap-2">
          {AREA_PRESETS.map((preset, idx) => {
            const isActive = areaMin === preset.min && areaMax === preset.max;
            return (
              <button
                key={idx}
                type="button"
                onClick={() => onAreaChange(preset.min, preset.max)}
                className={`px-2.5 py-2 rounded-xl text-center text-xs font-medium transition-all cursor-pointer ${
                  isActive
                    ? "bg-[#0F5F58] text-white shadow-xs font-semibold"
                    : "bg-[#FAF8F5] dark:bg-slate-900 text-[#4B5563] dark:text-slate-300 hover:bg-[#E7E2DA] dark:hover:bg-slate-800 border border-[#E7E2DA] dark:border-slate-800"
                }`}
              >
                {preset.label}
              </button>
            );
          })}
        </div>
      </div>
    </aside>
  );
};
