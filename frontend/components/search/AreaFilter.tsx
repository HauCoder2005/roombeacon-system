"use client";

import React, { useState, useRef, useEffect, useMemo } from "react";
import { ChevronDown, Check } from "lucide-react";

interface AreaFilterProps {
  minArea?: number;
  maxArea?: number;
  onChange: (min?: number, max?: number) => void;
  className?: string;
}

const PRESET_AREAS = [
  { label: "Tất cả diện tích", min: undefined, max: undefined },
  { label: "Dưới 20 m²", min: undefined, max: 20 },
  { label: "20 – 30 m²", min: 20, max: 30 },
  { label: "30 – 50 m²", min: 30, max: 50 },
  { label: "Trên 50 m²", min: 50, max: undefined },
];

export const AreaFilter: React.FC<AreaFilterProps> = ({
  minArea,
  maxArea,
  onChange,
  className = "",
}) => {
  const [isOpen, setIsOpen] = useState(false);
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
    if (minArea === undefined && maxArea === undefined) return "m²";
    if (minArea === undefined && maxArea === 20) return "< 20 m²";
    if (minArea === 20 && maxArea === 30) return "20–30 m²";
    if (minArea === 30 && maxArea === 50) return "30–50 m²";
    if (minArea === 50 && maxArea === undefined) return "> 50 m²";

    if (minArea && maxArea) return `${minArea}–${maxArea} m²`;
    if (minArea) return `> ${minArea} m²`;
    if (maxArea) return `< ${maxArea} m²`;
    return "m²";
  }, [minArea, maxArea]);

  const isPresetActive = (min?: number, max?: number) => {
    return minArea === min && maxArea === max;
  };

  const handleSelect = (min?: number, max?: number) => {
    onChange(min, max);
    setIsOpen(false);
  };

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-xl transition-colors hover:bg-bg ${
          minArea !== undefined || maxArea !== undefined
            ? "text-brand font-semibold"
            : "text-ink"
        }`}
        aria-expanded={isOpen}
      >
        <span className="truncate max-w-[80px]">{label}</span>
        <ChevronDown className="w-3.5 h-3.5 text-ink-muted shrink-0" />
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full mt-2 w-52 bg-surface rounded-2xl shadow-xl border border-border p-3 z-50 animate-fade-in">
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider mb-2 px-1">
            Chọn diện tích
          </div>

          <div className="space-y-1">
            {PRESET_AREAS.map((preset, idx) => {
              const active = isPresetActive(preset.min, preset.max);
              return (
                <button
                  key={idx}
                  type="button"
                  onClick={() => handleSelect(preset.min, preset.max)}
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
        </div>
      )}
    </div>
  );
};
