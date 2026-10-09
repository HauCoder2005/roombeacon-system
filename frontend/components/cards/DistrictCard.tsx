import React from "react";
import Link from "next/link";
import type { DistrictCard as DistrictCardType } from "@/lib/types/api";
import { formatListingCount, formatPrice, formatPricePerM2 } from "@/lib/format";
import { PriceRangeStrip } from "./PriceRangeStrip";
import { ChevronRight } from "lucide-react";

interface DistrictCardProps {
  card: DistrictCardType;
  className?: string;
}

/** "Quận 7" -> "7", "Quận Bình Thạnh" -> "BT", "Thành phố Thủ Đức" -> "TĐ". */
function placeholderMark(name: string): string {
  const rest = name.replace(/^(Quận|Huyện|Thành phố|TP\.?)\s+/i, "").trim();
  if (/^\d+$/.test(rest)) return rest;
  return rest
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 3)
    .toUpperCase();
}

export const DistrictCard: React.FC<DistrictCardProps> = ({
  card,
  className = "",
}) => {
  const isLowData = card.stats.priced_listing_count < 30;
  const coverUrl = card.cover_image?.url
    ? card.cover_image.url.replace(/^\/api\/v1\//, "/api/rb/")
    : null;

  return (
    <article
      className={`group rounded-[20px] bg-white dark:bg-[#1A2234] border border-[#E7E2DA] dark:border-slate-800 overflow-hidden hover:shadow-[0_14px_30px_rgba(17,24,39,0.06)] hover:border-[#0F5F58]/50 transition-all duration-300 flex flex-col justify-between ${className}`}
    >
      <div>
        {/* 16:9 Cover Image header with dark gradient overlay; brand pattern fallback if null */}
        <Link
          href={`/khu-vuc/${card.id}`}
          className="relative h-44 w-full block overflow-hidden bg-[#FAF8F5] dark:bg-slate-900 group/image"
          title={`Xem thị trường ${card.name}`}
        >
          {coverUrl ? (
            <img
              src={coverUrl}
              alt={`Khu vực ${card.name}`}
              loading="lazy"
              decoding="async"
              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
            />
          ) : (
            // No cover photo yet: an editorial placeholder instead of a stock image.
            <div
              className="relative flex h-full w-full items-start justify-end overflow-hidden bg-gradient-to-br from-[#0F5F58] via-[#004640] to-[#00201D] p-4"
              aria-hidden
            >
              <svg className="absolute inset-0 h-full w-full opacity-[0.12]" viewBox="0 0 200 120" preserveAspectRatio="xMidYMid slice">
                <path d="M0 95 L30 95 L30 60 L48 60 L48 80 L70 80 L70 40 L92 40 L92 75 L110 75 L110 52 L132 52 L132 88 L150 88 L150 30 L172 30 L172 70 L200 70 L200 120 L0 120 Z" fill="#FCC665" />
              </svg>
              <span className="relative font-display text-[64px] italic leading-none text-[#FCC665]/25 transition-transform duration-500 group-hover:scale-105">
                {placeholderMark(card.name)}
              </span>
            </div>
          )}

          {/* Dark gradient overlay for text readability */}
          <div className="absolute inset-0 bg-gradient-to-t from-black/65 via-transparent to-transparent pointer-events-none" />

          {/* Overlay text: District name & listing count */}
          <div className="absolute bottom-3 left-4 right-4 flex items-center justify-between text-white">
            <span className="font-display text-[19px] font-semibold text-white tracking-tight drop-shadow-xs">
              {card.name}
            </span>
            <span className="text-[11px] font-semibold bg-white/20 backdrop-blur-md px-2.5 py-0.5 rounded-full border border-white/20 text-white">
              {formatListingCount(card.stats.listing_count)}
            </span>
          </div>
        </Link>

        {/* Card Body: Price metrics & Range strip */}
        <div className="p-5 flex-1 flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-baseline justify-between">
              <span className="text-[19px] font-bold text-[#111827] dark:text-white font-sans">
                {formatPrice(card.price.median, { shortUnit: true })}
                <span className="text-xs font-normal text-[#6B7280] dark:text-slate-400 ml-1">
                  /tháng
                </span>
              </span>
              <span className="text-[11px] font-medium text-[#6B7280] dark:text-slate-400">
                {formatPricePerM2(card.price.median_per_m2)}
              </span>
            </div>
            <div className="flex items-center justify-between mt-0.5">
              <span className="text-[11px] text-[#6B7280] dark:text-slate-400">
                Giá trung vị
              </span>
              {isLowData && (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-[#FAF8F5] dark:bg-slate-800 text-[#6B7280] border border-[#E7E2DA]">
                  Ít dữ liệu
                </span>
              )}
            </div>
          </div>

          {/* Signature Price Strip */}
          <div className="space-y-1.5 pt-2 border-t border-[#FAF8F5] dark:border-slate-800">
            <div className="flex justify-between text-[11px] text-[#6B7280] dark:text-slate-400">
              <span>Phổ giá p25–p75</span>
              <span className="font-semibold text-[#111827] dark:text-slate-200">
                {card.price.p25 && card.price.p75
                  ? `${formatPrice(card.price.p25, { shortUnit: true })} – ${formatPrice(card.price.p75, { shortUnit: true })}`
                  : "Chưa đủ số liệu"}
              </span>
            </div>
            <PriceRangeStrip price={card.price} size="sm" showLabels={false} />
          </div>
        </div>
      </div>

      {/* Action links */}
      <div className="px-5 py-3 bg-[#FAF8F5]/60 dark:bg-slate-900/40 border-t border-[#E7E2DA] dark:border-slate-800 flex items-center justify-between text-xs font-medium">
        <Link
          href={`/khu-vuc/${card.id}`}
          className="text-[#0F5F58] dark:text-[#91D6CD] hover:underline flex items-center gap-1 font-semibold"
        >
          Chi tiết khu vực
          <ChevronRight className="w-3.5 h-3.5" />
        </Link>
        <Link
          href={`/tim-phong?district_id=${card.id}&district_name=${encodeURIComponent(card.name)}`}
          className="text-[#6B7280] hover:text-[#111827] dark:text-slate-400 dark:hover:text-white transition-colors"
        >
          Xem phòng
        </Link>
      </div>
    </article>
  );
};
