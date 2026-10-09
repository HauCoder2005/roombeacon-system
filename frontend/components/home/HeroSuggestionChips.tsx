"use client";

import React from "react";
import { useRouter } from "next/navigation";

interface HeroSuggestionChipsProps {
  topDistricts: { id: string; name: string }[];
}

export const HeroSuggestionChips: React.FC<HeroSuggestionChipsProps> = ({ topDistricts }) => {
  const router = useRouter();

  const handleChipClick = (params: Record<string, string>) => {
    const searchParams = new URLSearchParams(params).toString();
    router.push(`/tim-phong?${searchParams}`);
  };

  return (
    <div className="mt-4 flex flex-wrap items-center justify-center gap-2 text-xs">
      <span className="text-ink-muted font-medium mr-1 flex items-center gap-1">
        Gợi ý:
      </span>
      <button
        type="button"
        onClick={() => handleChipClick({ price_max: "3000000" })}
        className="px-3 py-1.5 rounded-full bg-surface hover:bg-brand-soft/60 hover:text-brand border border-border text-ink transition-colors shadow-sm"
      >
        Dưới 3 triệu
      </button>
      <button
        type="button"
        onClick={() => handleChipClick({ price_min: "3000000", price_max: "5000000" })}
        className="px-3 py-1.5 rounded-full bg-surface hover:bg-brand-soft/60 hover:text-brand border border-border text-ink transition-colors shadow-sm"
      >
        3 – 5 triệu
      </button>
      {topDistricts.map((d) => (
        <button
          key={d.id}
          type="button"
          onClick={() => handleChipClick({ district_id: d.id, district_name: d.name })}
          className="px-3 py-1.5 rounded-full bg-surface hover:bg-brand-soft/60 hover:text-brand border border-border text-ink transition-colors shadow-sm"
        >
          {d.name}
        </button>
      ))}
    </div>
  );
};
