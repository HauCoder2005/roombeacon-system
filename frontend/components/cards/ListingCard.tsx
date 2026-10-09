"use client";

import { safeExternalUrl } from "@/lib/safeUrl";
import { trustworthyValuation } from "@/lib/valuation";
import React, { useState, useRef, useCallback } from "react";
import Link from "next/link";
import type { ListingCard as ListingCardType, Price } from "@/lib/types/api";
import {
  formatPrice,
  formatArea,
  formatPricePerM2,
  formatRelativeTime,
} from "@/lib/format";
import { PriceRangeStrip } from "./PriceRangeStrip";
import { ValuationBadge } from "./ValuationBadge";
import {
  MapPin,
  Clock,
  Building2,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

interface ListingCardProps {
  listing: ListingCardType;
  marketPrice?: Price | null;
  className?: string;
}

export const ListingCard: React.FC<ListingCardProps> = ({
  listing,
  marketPrice,
  className = "",
}) => {
  const priceAmount = listing.price?.amount ?? null;
  const valuation = trustworthyValuation(listing);
  const locationText = [
    listing.location?.ward?.name,
    listing.location?.district?.name,
  ]
    .filter(Boolean)
    .join(", ");

  const previewUrls = (listing.images?.preview || []).map((url) =>
    url.replace(/^\/api\/v1\//, "/api/rb/")
  );
  const hasPreview = previewUrls.length > 0;
  const [currentIndex, setCurrentIndex] = useState(0);
  const [hasInteracted, setHasInteracted] = useState(false);
  const touchStartXRef = useRef<number | null>(null);

  const handlePrev = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setHasInteracted(true);
      setCurrentIndex((prev) => (prev > 0 ? prev - 1 : previewUrls.length - 1));
    },
    [previewUrls.length]
  );

  const handleNext = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setHasInteracted(true);
      setCurrentIndex((prev) =>
        prev < previewUrls.length - 1 ? prev + 1 : 0
      );
    },
    [previewUrls.length]
  );

  const handleDotClick = useCallback(
    (e: React.MouseEvent, index: number) => {
      e.preventDefault();
      e.stopPropagation();
      setHasInteracted(true);
      setCurrentIndex(index);
    },
    []
  );

  const handleTouchStart = (e: React.TouchEvent) => {
    setHasInteracted(true);
    touchStartXRef.current = e.touches[0].clientX;
  };

  const handleTouchEnd = (e: React.TouchEvent) => {
    if (touchStartXRef.current === null) return;
    const touchEndX = e.changedTouches[0].clientX;
    const diff = touchEndX - touchStartXRef.current;
    touchStartXRef.current = null;
    if (diff > 40) {
      setCurrentIndex((prev) => (prev > 0 ? prev - 1 : previewUrls.length - 1));
    } else if (diff < -40) {
      setCurrentIndex((prev) =>
        prev < previewUrls.length - 1 ? prev + 1 : 0
      );
    }
  };

  return (
    <article
      className={`group rounded-[20px] bg-white dark:bg-[#1A2234] border border-[#E7E2DA] dark:border-slate-800 overflow-hidden hover:shadow-[0_14px_36px_rgba(17,24,39,0.08)] hover:-translate-y-0.5 transition-all duration-300 flex flex-col justify-between ${className}`}
    >
      <div>
        {/* 4:3 Media: Carousel if preview images available, otherwise placeholder */}
        {hasPreview ? (
          <div
            className="relative aspect-[4/3] w-full overflow-hidden bg-[#FAF8F5] dark:bg-slate-900 group/carousel select-none"
            onMouseEnter={() => setHasInteracted(true)}
            onTouchStart={handleTouchStart}
            onTouchEnd={handleTouchEnd}
          >
            <Link
              href={`/phong/${listing.id}`}
              className="block w-full h-full relative"
              title={listing.title}
            >
              <img
                src={previewUrls[currentIndex]}
                alt={`${listing.title} - ảnh ${currentIndex + 1}`}
                loading={currentIndex === 0 ? "eager" : "lazy"}
                decoding="async"
                className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/40 via-transparent to-black/20 pointer-events-none" />
            </Link>

            {/* Lazy load image 2+ only after user interaction */}
            {hasInteracted &&
              previewUrls.map((url, i) =>
                i !== currentIndex ? (
                  <link key={url} rel="prefetch" href={url} as="image" />
                ) : null
              )}

            {/* Top-left: Valuation badge */}
            <div className="absolute top-3 left-3 z-10 pointer-events-none">
              {valuation ? (
                <span
                  className={`text-[11px] px-2.5 py-1 rounded-full font-semibold shadow-xs flex items-center gap-1 backdrop-blur-sm ${
                    valuation.label === "BELOW_ESTIMATE"
                      ? "bg-emerald-50/95 text-[#047857] border border-emerald-200/80"
                      : valuation.label === "ABOVE_ESTIMATE"
                      ? "bg-red-50/95 text-[#B91C1C] border border-red-200/80"
                      : "bg-white/95 text-[#374151] border border-[#E7E2DA]"
                  }`}
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-current"></span>
                  {valuation.label === "BELOW_ESTIMATE"
                    ? `Rẻ hơn ước tính ${Math.abs(Math.round(valuation.delta_pct))}%`
                    : valuation.label === "ABOVE_ESTIMATE"
                    ? `Cao hơn ước tính ${Math.round(valuation.delta_pct)}%`
                    : "Đúng giá thị trường"}
                </span>
              ) : (
                <span className="text-[10px] font-semibold uppercase tracking-wider bg-black/60 text-white px-2 py-0.5 rounded-md backdrop-blur-xs">
                  {listing.source}
                </span>
              )}
            </div>

            {/* Photo counter if multiple */}
            {previewUrls.length > 1 && (
              <span className="absolute bottom-3 right-3 px-2 py-0.5 rounded-md bg-black/60 text-white text-[10px] font-medium backdrop-blur-sm pointer-events-none z-10">
                {currentIndex + 1}/{listing.images?.count || previewUrls.length}
              </span>
            )}

            {/* Hover Prev/Next Arrows (desktop) */}
            {previewUrls.length > 1 && (
              <>
                <button
                  type="button"
                  onClick={handlePrev}
                  aria-label="Ảnh trước"
                  className="absolute left-2 top-1/2 -translate-y-1/2 w-7 h-7 rounded-full bg-black/60 hover:bg-black/85 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 group-hover/carousel:opacity-100 transition-opacity z-20 shadow-md backdrop-blur-sm cursor-pointer"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={handleNext}
                  aria-label="Ảnh tiếp theo"
                  className="absolute right-2 top-1/2 -translate-y-1/2 w-7 h-7 rounded-full bg-black/60 hover:bg-black/85 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 group-hover/carousel:opacity-100 transition-opacity z-20 shadow-md backdrop-blur-sm cursor-pointer"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </>
            )}

            {/* Position Dots Indicator */}
            {previewUrls.length > 1 && (
              <div className="absolute bottom-2.5 left-0 right-0 flex justify-center items-center gap-1.5 pointer-events-none z-10">
                {previewUrls.map((_, i) => (
                  <span
                    key={i}
                    className={`h-1.5 rounded-full transition-all ${
                      i === currentIndex
                        ? "w-4 bg-white shadow-xs"
                        : "w-1.5 bg-white/60"
                    }`}
                  />
                ))}
              </div>
            )}
          </div>
        ) : (
          <Link
            href={`/phong/${listing.id}`}
            className="block relative aspect-[4/3] w-full bg-gradient-to-br from-[#FAF8F5] via-[#F3EFEA] to-[#E7E2DA] dark:from-slate-900 dark:via-slate-800 dark:to-slate-900 flex flex-col items-center justify-center p-4 overflow-hidden group/thumb"
          >
            <Building2 className="w-12 h-12 text-[#0F5F58]/35 dark:text-[#91D6CD]/40 group-hover/thumb:scale-110 transition-transform duration-300" />
            <span className="text-[11px] font-medium text-[#6B7280] dark:text-slate-400 mt-1">
              Tin chưa có ảnh
            </span>

            {/* Top-left: Valuation badge if present */}
            {valuation && (
              <div className="absolute top-3 left-3 z-10">
                <span
                  className={`text-[11px] px-2.5 py-1 rounded-full font-semibold shadow-xs flex items-center gap-1 ${
                    valuation.label === "BELOW_ESTIMATE"
                      ? "bg-emerald-50 text-[#047857] border border-emerald-200"
                      : valuation.label === "ABOVE_ESTIMATE"
                      ? "bg-red-50 text-[#B91C1C] border border-red-200"
                      : "bg-white text-[#374151] border border-[#E7E2DA]"
                  }`}
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-current"></span>
                  {valuation.label === "BELOW_ESTIMATE"
                    ? `Rẻ hơn ước tính ${Math.abs(Math.round(valuation.delta_pct))}%`
                    : valuation.label === "ABOVE_ESTIMATE"
                    ? `Cao hơn ước tính ${Math.round(valuation.delta_pct)}%`
                    : "Đúng giá thị trường"}
                </span>
              </div>
            )}

            {/* Source badge */}
            <span className="absolute bottom-3 left-3 px-2 py-0.5 rounded-md bg-black/60 text-white text-[10px] font-medium backdrop-blur-sm">
              {listing.source}
            </span>
          </Link>
        )}

        {/* Card Body */}
        <div className="p-5 flex-1 flex flex-col justify-between space-y-4">
          <div>
            {/* Price & Time */}
            <div className="flex items-baseline justify-between mb-1">
              <span className="text-[19px] font-bold text-[#111827] dark:text-white font-sans">
                {formatPrice(priceAmount, { shortUnit: false })}
                <span className="text-xs font-normal text-[#6B7280] dark:text-slate-400 ml-1">
                  /tháng
                </span>
              </span>
              <span className="text-[11px] text-[#6B7280] dark:text-slate-400">
                {formatRelativeTime(listing.last_observed_at)}
              </span>
            </div>

            {/* Area & Price/m² */}
            <div className="flex items-center gap-2 text-xs text-[#4B5563] dark:text-slate-400 mb-2">
              <span>{formatArea(listing.area_m2)}</span>
              <span className="text-[#E7E2DA] dark:text-slate-700">·</span>
              <span>{formatPricePerM2(listing.price_per_m2)}</span>
            </div>

            {/* Title */}
            <h3 className="font-display text-[17px] font-medium text-[#111827] dark:text-white line-clamp-2 leading-snug group-hover:text-[#0F5F58] dark:group-hover:text-[#91D6CD] transition-colors mb-2">
              <Link href={`/phong/${listing.id}`}>{listing.title}</Link>
            </h3>

            {/* Location */}
            <div className="flex items-center gap-1.5 text-xs text-[#6B7280] dark:text-slate-400 truncate">
              <MapPin className="w-3.5 h-3.5 text-[#0F5F58] shrink-0" />
              <span className="truncate">{locationText || "TP. Hồ Chí Minh"}</span>
            </div>
          </div>

          {/* Sub-district Price Range Strip at bottom */}
          {marketPrice && priceAmount && (
            <div className="pt-3 border-t border-[#FAF8F5] dark:border-slate-800 space-y-1">
              <div className="flex justify-between text-[11px] text-[#6B7280] dark:text-slate-400">
                <span>Vị trí giá: {listing.location?.ward?.name || listing.location?.district?.name || "Khu vực"}</span>
                <span
                  className={`font-semibold ${
                    priceAmount < (marketPrice.p25 ?? 0)
                      ? "text-[#047857]"
                      : priceAmount > (marketPrice.p75 ?? Infinity)
                      ? "text-[#B91C1C]"
                      : "text-[#0F5F58]"
                  }`}
                >
                  {priceAmount < (marketPrice.p25 ?? 0)
                    ? "Ưu đãi cao"
                    : priceAmount > (marketPrice.p75 ?? Infinity)
                    ? "Phân khúc cao"
                    : "Hợp lý"}
                </span>
              </div>
              <PriceRangeStrip
                price={marketPrice}
                currentPrice={priceAmount}
                size="sm"
                showLabels={false}
              />
            </div>
          )}
        </div>
      </div>

      {/* Footer link to detail & source */}
      <div className="px-5 py-3 bg-[#FAF8F5]/60 dark:bg-slate-900/40 border-t border-[#E7E2DA] dark:border-slate-800 flex items-center justify-between text-xs font-medium">
        <Link
          href={`/phong/${listing.id}`}
          className="text-[#0F5F58] dark:text-[#91D6CD] font-semibold hover:underline"
        >
          Xem chi tiết →
        </Link>
        {safeExternalUrl(listing.source_url) && (
          <a
            href={safeExternalUrl(listing.source_url)!}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="text-[#6B7280] hover:text-[#111827] dark:text-slate-400 dark:hover:text-white flex items-center gap-1 text-[11px] transition-colors"
            title="Mở tin đăng gốc trên trang nguồn"
          >
            <span>Tin gốc</span>
            <ExternalLink className="w-3 h-3" />
          </a>
        )}
      </div>
    </article>
  );
};
