import React from "react";
import Link from "next/link";
import { ArrowRight, BarChart3, Info } from "lucide-react";
import type { DistrictCard, WardCard } from "@/lib/types/api";
import { formatArea, formatListingCount, formatPrice, formatPricePerM2 } from "@/lib/format";
import { PriceRangeStrip } from "./PriceRangeStrip";

interface MarketPriceBadgeProps {
  locationName: string;
  cardData?: DistrictCard | WardCard | null;
  className?: string;
}

/** Market card for the search sidebar — every number comes from the location card API. */
export const MarketPriceBadge: React.FC<MarketPriceBadgeProps> = ({ locationName, cardData, className = "" }) => {
  if (!cardData) {
    return (
      <aside className={`rounded-2xl border border-border bg-surface p-6 ${className}`}>
        <div className="flex items-start gap-2 text-sm text-ink-muted">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-brand" strokeWidth={1.6} aria-hidden />
          <p>Chọn một quận hoặc phường để xem giá thị trường của khu vực đó.</p>
        </div>
      </aside>
    );
  }

  const { price, stats } = cardData;
  const districtId = cardData.type === "district" ? cardData.id : cardData.district.id;

  return (
    <aside className={`space-y-6 rounded-2xl border border-border bg-surface p-6 ${className}`}>
      <header className="space-y-1">
        <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-beacon">
          <BarChart3 className="h-3.5 w-3.5" strokeWidth={1.8} aria-hidden />
          Giá thị trường
        </p>
        <h2 className="font-display text-[22px] font-medium leading-snug text-brand">Thị trường {locationName}</h2>
      </header>

      <div className="space-y-3 rounded-xl bg-bg-alt p-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-muted">Giá thuê trung vị</p>
        <p className="font-sans text-[30px] font-bold leading-none tracking-tight text-brand">
          {formatPrice(price.median, { shortUnit: true })}
          <span className="ml-1 text-sm font-medium text-ink-muted">/tháng</span>
        </p>
        <dl className="grid grid-cols-2 gap-2 border-t border-border-subtle pt-3 text-[12px]">
          <div>
            <dt className="text-ink-muted">Số tin</dt>
            <dd className="font-semibold text-ink">{formatListingCount(stats.listing_count)}</dd>
          </div>
          <div>
            <dt className="text-ink-muted">Có giá hợp lệ</dt>
            <dd className="font-semibold text-ink">{formatListingCount(stats.priced_listing_count)}</dd>
          </div>
        </dl>
      </div>

      <div className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-muted">Dải giá phổ biến (p25 – p75)</p>
        <div className="rounded-xl border border-border-subtle bg-bg-alt p-3">
          <PriceRangeStrip price={price} size="md" showLabels />
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-3 text-[13px]">
        <div className="rounded-xl border border-border-subtle p-3">
          <dt className="text-[11px] text-ink-muted">Giá trung vị / m²</dt>
          <dd className="mt-1 font-semibold text-ink">{formatPricePerM2(price.median_per_m2)}</dd>
        </div>
        <div className="rounded-xl border border-border-subtle p-3">
          <dt className="text-[11px] text-ink-muted">Diện tích trung vị</dt>
          <dd className="mt-1 font-semibold text-ink">{formatArea(price.median_area_m2)}</dd>
        </div>
      </dl>

      <p className="text-[12px] leading-relaxed text-ink-muted">
        Tính trên các tin cho thuê có giá hợp lệ trong khu vực; dải p25–p75 là mức giá của một nửa số tin ở giữa.
      </p>

      <Link
        href={`/khu-vuc/${districtId}`}
        className="group flex items-center justify-center gap-1.5 rounded-xl py-2.5 text-[13px] font-semibold text-brand hover:bg-brand/10"
      >
        Xem trang khu vực
        <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
      </Link>
    </aside>
  );
};
