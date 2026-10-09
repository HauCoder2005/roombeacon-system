import React from "react";
import type { ListingValuation } from "@/lib/types/api";
import { TrendingDown, TrendingUp, Minus } from "lucide-react";

interface ValuationBadgeProps {
  valuation: ListingValuation | null | undefined;
  className?: string;
}

export const ValuationBadge: React.FC<ValuationBadgeProps> = ({
  valuation,
  className = "",
}) => {
  if (!valuation) return null;

  const { delta_pct, label } = valuation;
  const absDelta = Math.abs(Math.round(delta_pct));

  if (label === "BELOW_ESTIMATE") {
    return (
      <span
        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-good dark:bg-emerald-950/60 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800 ${className}`}
      >
        <TrendingDown className="w-3.5 h-3.5" />
        Rẻ hơn ước tính {absDelta}%
      </span>
    );
  }

  if (label === "ABOVE_ESTIMATE") {
    return (
      <span
        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-bad dark:bg-rose-950/60 dark:text-rose-400 border border-rose-200 dark:border-rose-800 ${className}`}
      >
        <TrendingUp className="w-3.5 h-3.5" />
        Cao hơn ước tính {absDelta}%
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-ink-muted dark:bg-slate-800 border border-border ${className}`}
    >
      <Minus className="w-3.5 h-3.5" />
      Sát ước tính
    </span>
  );
};
