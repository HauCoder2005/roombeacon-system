import React from "react";
import Link from "next/link";
import type { WardCard as WardCardType } from "@/lib/types/api";
import { formatListingCount, formatPrice, formatPricePerM2 } from "@/lib/format";
import { PriceRangeStrip } from "./PriceRangeStrip";
import { MapPin, ArrowRight } from "lucide-react";

interface WardCardProps {
  card: WardCardType;
  className?: string;
}

export const WardCard: React.FC<WardCardProps> = ({ card, className = "" }) => {
  const isLowData = card.stats.priced_listing_count < 30;
  const coverUrl = card.cover_image?.url
    ? card.cover_image.url.replace(/^\/api\/v1\//, "/api/rb/")
    : null;
  const wardSearchHref = `/tim-phong?district_id=${card.district.id}&ward_id=${card.id}`;

  return (
    <article
      className={`group rounded-[20px] bg-white dark:bg-[#1A2234] border border-[#E7E2DA] dark:border-slate-800 overflow-hidden hover:shadow-[0_14px_30px_rgba(17,24,39,0.06)] hover:border-[#0F5F58]/50 transition-all duration-300 flex flex-col justify-between ${className}`}
    >
      <div>
        {/* 16:9 Cover Image Header with Dark Gradient */}
        <Link
          href={wardSearchHref}
          className="relative h-40 sm:h-44 w-full block overflow-hidden bg-[#FAF8F5] dark:bg-slate-900 group/image"
          title={`Tìm phòng tại ${card.name}, ${card.district.name}`}
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
            <div className="w-full h-full bg-gradient-to-br from-[#0F5F58]/20 via-[#0F5F58]/10 to-[#B8892E]/20 flex items-center justify-center relative overflow-hidden">
              <MapPin className="w-8 h-8 text-[#0F5F58]/40 group-hover:scale-110 transition-transform duration-300" />
            </div>
          )}

          {/* Dark gradient overlay for text readability */}
          <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/25 to-transparent pointer-events-none" />

          {/* Overlay text */}
          <div className="absolute bottom-3 left-4 right-4 flex items-center justify-between text-white">
            <span className="font-display text-lg font-medium text-white truncate drop-shadow-sm">
              {card.name}
            </span>
            <span className="text-[11px] font-medium bg-white/20 backdrop-blur-md px-2.5 py-0.5 rounded-full border border-white/20 whitespace-nowrap">
              {formatListingCount(card.stats.listing_count)}
            </span>
          </div>
        </Link>

        {/* Card Body */}
        <div className="p-5 flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-baseline justify-between">
              <span className="text-xl font-bold text-[#111827] dark:text-white font-sans">
                {formatPrice(card.price.median, { perMonth: false, shortUnit: false })}
                <span className="text-xs font-normal text-[#6B7280] dark:text-slate-400 ml-1">
                  /tháng
                </span>
              </span>
              <span className="text-xs text-[#6B7280] dark:text-slate-400 font-medium">
                {formatPricePerM2(card.price.median_per_m2)}
              </span>
            </div>
            <span className="text-xs text-[#6B7280] dark:text-slate-400 block mt-0.5">
              Giá trung vị
            </span>
          </div>

          {/* Range strip */}
          <div className="space-y-1.5 pt-2 border-t border-[#FAF8F5] dark:border-slate-800">
            <PriceRangeStrip price={card.price} size="sm" showLabels={true} />
          </div>
        </div>
      </div>

      {/* Footer Link */}
      <div className="px-5 py-3 bg-[#FAF8F5]/60 dark:bg-slate-900/40 border-t border-[#E7E2DA] dark:border-slate-800 flex items-center justify-between text-xs font-medium">
        <Link
          href={`/dinh-gia?district_id=${card.district.id}&ward_id=${card.id}`}
          className="text-[#6B7280] hover:text-[#0F5F58] dark:hover:text-[#91D6CD] transition-colors"
        >
          Định giá phường này
        </Link>
        <Link
          href={wardSearchHref}
          className="text-[#0F5F58] dark:text-[#91D6CD] font-semibold hover:underline flex items-center gap-1"
        >
          <span>Tìm phòng</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>
    </article>
  );
};
