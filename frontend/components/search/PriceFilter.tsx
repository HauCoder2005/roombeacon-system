"use client";

import React, { useState, useRef, useEffect, useMemo } from "react";
import { ChevronDown, Check } from "lucide-react";

interface PriceFilterProps {
  minPrice?: number;
  maxPrice?: number;
  onChange: (min?: number, max?: number) => void;
  className?: string;
}

const PRESET_RANGES = [
  { label: "Tất cả mức giá", min: undefined, max: undefined },
  { label: "Dưới 2 triệu", min: undefined, max: 2000000 },
  { label: "2 – 3 triệu", min: 2000000, max: 3000000 },
  { label: "3 – 5 triệu", min: 3000000, max: 5000000 },
  { label: "5 – 8 triệu", min: 5000000, max: 8000000 },
  { label: "Trên 8 triệu", min: 8000000, max: undefined },
];

export const PriceFilter: React.FC<PriceFilterProps> = ({
  minPrice,
  maxPrice,
  onChange,
  className = "",
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [customMin, setCustomMin] = useState(minPrice ? String(minPrice / 1_000_000) : "");
  const [customMax, setCustomMax] = useState(maxPrice ? String(maxPrice / 1_000_000) : "");
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const label = useMemo(() => {
    if (minPrice === undefined && maxPrice === undefined) return "Giá";
    if (minPrice === undefined && maxPrice === 2000000) return "< 2 tr";
    if (minPrice === 2000000 && maxPrice === 3000000) return "2 – 3 tr";
    if (minPrice === 3000000 && maxPrice === 5000000) return "3 – 5 tr";
    if (minPrice === 5000000 && maxPrice === 8000000) return "5 – 8 tr";
    if (minPrice === 8000000 && maxPrice === undefined) return "> 8 tr";

    if (minPrice && maxPrice) {
      return `${minPrice / 1_000_000} – ${maxPrice / 1_000_000} tr`;
    }
    if (minPrice) return `> ${minPrice / 1_000_000} tr`;
    if (maxPrice) return `< ${maxPrice / 1_000_000} tr`;
    return "Giá";
  }, [minPrice, maxPrice]);

  const handleSelectPreset = (min?: number, max?: number) => {
    onChange(min, max);
    setCustomMin(min ? String(min / 1_000_000) : "");
    setCustomMax(max ? String(max / 1_000_000) : "");
    setIsOpen(false);
  };

  const handleApplyCustom = (e: React.FormEvent) => {
    e.preventDefault();
    const minVal = customMin ? parseFloat(customMin) * 1_000_000 : undefined;
    const maxVal = customMax ? parseFloat(customMax) * 1_000_000 : undefined;
    onChange(minVal, maxVal);
    setIsOpen(false);
  };

  const isPresetActive = (min?: number, max?: number) => {
    return minPrice === min && maxPrice === max;
  };

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-xl transition-colors hover:bg-bg ${
          minPrice !== undefined || maxPrice !== undefined
            ? "text-brand font-semibold"
            : "text-ink"
        }`}
        aria-expanded={isOpen}
      >
        <span className="truncate max-w-[90px]">{label}</span>
        <ChevronDown className="w-3.5 h-3.5 text-ink-muted shrink-0" />
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full mt-2 w-64 bg-surface rounded-2xl shadow-xl border border-border p-3 z-50 animate-fade-in">
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider mb-2 px-1">
            Chọn khoảng giá
          </div>

          <div className="space-y-1 mb-3">
            {PRESET_RANGES.map((preset, idx) => {
              const active = isPresetActive(preset.min, preset.max);
              return (
                <button
                  key={idx}
                  type="button"
                  onClick={() => handleSelectPreset(preset.min, preset.max)}
                  className={`w-full px-2.5 py-1.5 rounded-lg text-left text-xs flex items-center justify-between transition-colors ${
                    active
                      ? "bg-brand-soft/50 text-brand font-semibold"
                      : "text-ink hover:bg-bg"
                  }`}
                >
                  <span>{preset.label}</span>
                  {active && <Check className="w-3.5 h-3.5 text-brand" />}
                </button>
              );
            })}
          </div>

          <form onSubmit={handleApplyCustom} className="pt-2.5 border-t border-border">
            <div className="text-xs font-medium text-ink mb-1.5 px-1">Tuỳ chỉnh (triệu đ):</div>
            <div className="flex items-center gap-2 mb-2.5">
              <input
                type="number"
                step="0.5"
                min="0"
                placeholder="Từ"
                value={customMin}
                onChange={(e) => setCustomMin(e.target.value)}
                className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-border bg-bg focus:border-brand focus:ring-1 focus:ring-brand outline-none"
              />
              <span className="text-xs text-ink-muted">–</span>
              <input
                type="number"
                step="0.5"
                min="0"
                placeholder="Đến"
                value={customMax}
                onChange={(e) => setCustomMax(e.target.value)}
                className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-border bg-bg focus:border-brand focus:ring-1 focus:ring-brand outline-none"
              />
            </div>
            <div className="flex gap-2">
              <button
                type="submit"
                className="flex-1 py-1.5 bg-brand text-white rounded-lg text-xs font-semibold hover:bg-brand-hover transition-colors"
              >
                Áp dụng
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
