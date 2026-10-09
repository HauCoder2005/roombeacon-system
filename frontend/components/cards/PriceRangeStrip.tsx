import React from "react";
import { formatPrice } from "@/lib/format";

interface PriceRangeStripProps {
  price?: {
    median: number | null;
    p25: number | null;
    p75: number | null;
  } | null;
  currentPrice?: number | null;
  minScale?: number;
  maxScale?: number;
  showLabels?: boolean;
  size?: "sm" | "md" | "lg";
  className?: string;
}

export const PriceRangeStrip: React.FC<PriceRangeStripProps> = ({
  price,
  currentPrice = null,
  minScale,
  maxScale,
  showLabels = false,
  size = "md",
  className = "",
}) => {
  const p25 = price?.p25;
  const p75 = price?.p75;
  const median = price?.median;

  if (p25 === null || p75 === null || median === null || !p25 || !p75 || !median) {
    return (
      <div className={`flex flex-col gap-1 ${className}`}>
        <div className="h-2 w-full bg-border-subtle rounded-full overflow-hidden border border-dashed border-border" />
        <span className="text-[11px] text-ink-muted italic">Chưa đủ dữ liệu dải giá</span>
      </div>
    );
  }

  const allValues = [p25, p75, median];
  if (currentPrice) allValues.push(currentPrice);

  const calculatedMin = minScale ?? Math.min(...allValues) * 0.8;
  const calculatedMax = maxScale ?? Math.max(...allValues) * 1.2;
  const rangeSpan = Math.max(calculatedMax - calculatedMin, 1);

  const getPercent = (val: number) => {
    const raw = ((val - calculatedMin) / rangeSpan) * 100;
    return Math.min(Math.max(raw, 2), 98);
  };

  const leftPercent = getPercent(p25);
  const rightPercent = getPercent(p75);
  const widthPercent = Math.max(rightPercent - leftPercent, 4);
  const medianPercent = getPercent(median);
  const currentPricePercent = currentPrice ? getPercent(currentPrice) : null;

  const trackHeight = size === "sm" ? "h-1.5" : size === "lg" ? "h-3" : "h-2";
  const dotSize =
    size === "sm"
      ? "w-2.5 h-2.5 -top-0.5"
      : size === "lg"
        ? "w-4 h-4 -top-0.5"
        : "w-3 h-3 -top-0.5";

  return (
    <div className={`w-full flex flex-col gap-1.5 ${className}`}>
      <div
        className={`relative w-full ${trackHeight} bg-slate-100 dark:bg-slate-700/60 rounded-full select-none`}
        title={`Dải p25-p75: ${formatPrice(p25, { shortUnit: true })} - ${formatPrice(p75, { shortUnit: true })}, Trung vị: ${formatPrice(median, { shortUnit: true })}`}
      >
        {/* Shaded p25 - p75 span */}
        <div
          className="absolute top-0 bottom-0 bg-brand/25 dark:bg-brand/35 rounded-full"
          style={{
            left: `${leftPercent}%`,
            width: `${widthPercent}%`,
          }}
        />

        {/* Median amber dot */}
        <div
          className={`absolute rounded-full bg-beacon shadow-sm transform -translate-x-1/2 ${dotSize} ring-2 ring-white dark:ring-slate-900 z-10`}
          style={{ left: `${medianPercent}%` }}
          title={`Trung vị khu vực: ${formatPrice(median)}`}
        />

        {/* Current item price marker (when present in listing cards) */}
        {currentPricePercent !== null && (
          <div
            className="absolute top-[-4px] bottom-[-4px] w-1 bg-ink dark:bg-white rounded-full transform -translate-x-1/2 z-20 shadow"
            style={{ left: `${currentPricePercent}%` }}
            title={`Giá tin này: ${formatPrice(currentPrice)}`}
          />
        )}
      </div>

      {showLabels && (
        <div className="flex justify-between items-center text-[11px] text-ink-muted">
          <span>p25: {formatPrice(p25, { shortUnit: true })}</span>
          <span className="font-semibold text-beacon">
            Median: {formatPrice(median, { shortUnit: true })}
          </span>
          <span>p75: {formatPrice(p75, { shortUnit: true })}</span>
        </div>
      )}
    </div>
  );
};
