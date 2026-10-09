"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useListings, useDistrict, useDistrictWards } from "@/lib/api/hooks";
import { SearchBar } from "./SearchBar";
import { FilterSidebar } from "./FilterSidebar";
import { ListingCard } from "../cards/ListingCard";
import { MarketPriceBadge } from "../cards/MarketPriceBadge";
import { Pagination } from "../common/Pagination";
import { ErrorBanner } from "../common/ErrorBanner";
import { formatNumber } from "@/lib/format";
import { SlidersHorizontal, Inbox, X, Sparkles, ChevronRight } from "lucide-react";

export const SearchResultsView: React.FC = () => {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [mobileFilterOpen, setMobileFilterOpen] = useState(false);

  const districtId = searchParams.get("district_id") || undefined;
  const districtName = searchParams.get("district_name") || undefined;
  const wardId = searchParams.get("ward_id") || undefined;
  const wardName = searchParams.get("ward_name") || undefined;
  const q = searchParams.get("q") || undefined;
  const priceMin = searchParams.get("price_min")
    ? Number(searchParams.get("price_min"))
    : undefined;
  const priceMax = searchParams.get("price_max")
    ? Number(searchParams.get("price_max"))
    : undefined;
  const areaMin = searchParams.get("area_min")
    ? Number(searchParams.get("area_min"))
    : undefined;
  const areaMax = searchParams.get("area_max")
    ? Number(searchParams.get("area_max"))
    : undefined;
  const sort = (searchParams.get("sort") as any) || "-last_observed_at";
  const page = searchParams.get("page") ? Number(searchParams.get("page")) : 1;

  // Real district / ward data from BFF
  const { data: districtRes } = useDistrict(districtId);
  const { data: wardsRes } = useDistrictWards(districtId);

  const selectedWard = React.useMemo(() => {
    if (!wardId || !wardsRes?.data) return null;
    return wardsRes.data.find((w) => w.id === wardId) || null;
  }, [wardId, wardsRes]);

  const resolvedDistrictName = districtRes?.data?.name || districtName;
  const resolvedWardName = selectedWard?.name || wardName;
  const marketCard = selectedWard || districtRes?.data || null;
  const marketLocationName = selectedWard
    ? `${selectedWard.name}, ${selectedWard.district.name}`
    : districtRes?.data?.name || (districtName ? districtName : "Khu vực đang chọn");

  // Real listings from backend API
  const {
    data: listingsRes,
    isLoading: loadingListings,
    error: listingsError,
    refetch: refetchListings,
  } = useListings({
    district_id: districtId,
    ward_id: wardId,
    q,
    price_min: priceMin,
    price_max: priceMax,
    area_min: areaMin,
    area_max: areaMax,
    sort,
    page,
    per_page: 20,
  });

  const updateParam = (key: string, val?: string | number) => {
    const next = new URLSearchParams(searchParams.toString());
    if (val !== undefined && val !== "") {
      next.set(key, String(val));
    } else {
      next.delete(key);
    }
    if (key !== "page") {
      next.delete("page");
    }
    router.push(`/tim-phong?${next.toString()}`);
  };

  const handlePriceChange = (min?: number, max?: number) => {
    const next = new URLSearchParams(searchParams.toString());
    if (min !== undefined) next.set("price_min", String(min));
    else next.delete("price_min");
    if (max !== undefined) next.set("price_max", String(max));
    else next.delete("price_max");
    next.delete("page");
    router.push(`/tim-phong?${next.toString()}`);
  };

  const handleAreaChange = (min?: number, max?: number) => {
    const next = new URLSearchParams(searchParams.toString());
    if (min !== undefined) next.set("area_min", String(min));
    else next.delete("area_min");
    if (max !== undefined) next.set("area_max", String(max));
    else next.delete("area_max");
    next.delete("page");
    router.push(`/tim-phong?${next.toString()}`);
  };

  const handleResetFilters = () => {
    const next = new URLSearchParams();
    if (districtId) next.set("district_id", districtId);
    if (districtName) next.set("district_name", districtName);
    if (wardId) next.set("ward_id", wardId);
    if (wardName) next.set("ward_name", wardName);
    router.push(`/tim-phong?${next.toString()}`);
  };

  const listings = listingsRes?.data || [];
  const pagination = listingsRes?.meta?.pagination;
  const totalItems = pagination?.total_items || 0;
  const startIdx = pagination ? (pagination.page - 1) * pagination.per_page + 1 : 1;
  const endIdx = pagination
    ? Math.min(pagination.page * pagination.per_page, totalItems)
    : listings.length;

  return (
    <div className="min-h-screen bg-[#FAF8F5] dark:bg-slate-950 flex flex-col">
      {/* Top Search Bar & Breadcrumbs */}
      <section className="bg-white dark:bg-[#151D2C] border-b border-[#E7E2DA] dark:border-slate-800 py-6 px-6 md:px-12 shadow-xs">
        <div className="max-w-[1440px] mx-auto space-y-4">
          <SearchBar
            compact={true}
            showQuickChips={false}
            initialValues={{
              districtId,
              districtName: resolvedDistrictName,
              wardId,
              wardName: resolvedWardName,
              q,
              priceMin,
              priceMax,
              areaMin,
              areaMax,
            }}
          />

          {/* Breadcrumbs & Result Meta */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between text-xs text-[#6B7280] dark:text-slate-400 gap-2 pt-1">
            <div className="flex items-center gap-1.5 flex-wrap">
              <Link href="/" className="hover:text-[#0F5F58] transition-colors">
                Trang chủ
              </Link>
              <span>/</span>
              <span className="text-[#111827] dark:text-white font-medium">TP. Hồ Chí Minh</span>
              {resolvedDistrictName && (
                <>
                  <span>/</span>
                  <span className="text-[#111827] dark:text-white font-medium">{resolvedDistrictName}</span>
                </>
              )}
              {resolvedWardName && (
                <>
                  <span>/</span>
                  <span className="text-[#0F5F58] dark:text-[#91D6CD] font-semibold">{resolvedWardName}</span>
                </>
              )}
            </div>

            <div className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-[#0F5F58] dark:text-[#91D6CD] font-bold">
              <span className="w-2 h-2 rounded-full bg-[#0F5F58] inline-block animate-pulse" />
              <span>{formatNumber(totalItems)} căn phòng phù hợp tiêu chí</span>
            </div>
          </div>
        </div>
      </section>

      {/* 3-COLUMN EDITORIAL WORKSPACE */}
      <main className="max-w-[1440px] mx-auto px-6 md:px-12 py-8 w-full flex-1">
        {/* Mobile Filter Toggle */}
        <div className="lg:hidden flex items-center justify-between mb-6">
          <button
            type="button"
            onClick={() => setMobileFilterOpen(true)}
            className="flex items-center gap-2 px-4 py-2.5 bg-white dark:bg-slate-900 rounded-full border border-[#E7E2DA] dark:border-slate-800 text-xs font-semibold text-[#111827] dark:text-white shadow-sm cursor-pointer"
          >
            <SlidersHorizontal className="w-4 h-4 text-[#0F5F58]" />
            <span>Bộ lọc &amp; Sắp xếp</span>
          </button>
          <span className="text-xs text-[#6B7280] font-medium">
            {formatNumber(totalItems)} tin
          </span>
        </div>

        {/* 3-Column Desktop Layout */}
        <div className="grid grid-cols-12 gap-8 items-start">
          {/* Left Column: Filter Sidebar (col-span-12 lg:col-span-3) */}
          <aside className="hidden lg:block lg:col-span-3 sticky top-24 space-y-6">
            <FilterSidebar
              priceMin={priceMin}
              priceMax={priceMax}
              areaMin={areaMin}
              areaMax={areaMax}
              sort={sort}
              onPriceChange={handlePriceChange}
              onAreaChange={handleAreaChange}
              onSortChange={(val) => updateParam("sort", val)}
              onReset={handleResetFilters}
            />
          </aside>

          {/* Middle Column: Listings Grid (col-span-12 lg:col-span-6) */}
          <div className="col-span-12 lg:col-span-6 space-y-6">
            {listingsError && (
              <ErrorBanner error={listingsError} onRetry={refetchListings} />
            )}

            <h1 className="font-display text-[28px] sm:text-[34px] font-medium leading-tight text-ink">
              Phòng cho thuê tại {resolvedWardName || resolvedDistrictName || "TP.HCM"}
            </h1>

            <div className="flex items-center justify-between bg-white dark:bg-slate-900 rounded-2xl p-4 border border-[#E7E2DA] dark:border-slate-800 text-xs shadow-xs">
              <span className="text-[#6B7280] dark:text-slate-400">
                {totalItems > 0 ? (
                  <>
                    Hiển thị{" "}
                    <strong className="text-[#111827] dark:text-white font-semibold">
                      {startIdx}–{endIdx}
                    </strong>{" "}
                    trên{" "}
                    <strong className="text-[#111827] dark:text-white font-semibold">
                      {formatNumber(totalItems)}
                    </strong>{" "}
                    căn phòng
                  </>
                ) : (
                  "Không có kết quả nào"
                )}
              </span>
              <span className="inline-flex items-center gap-1.5 text-[11px] text-[#0F5F58] dark:text-[#91D6CD] font-semibold uppercase tracking-wider">
                <Sparkles className="w-3.5 h-3.5 text-[#B8892E]" />
                Tin đăng đã làm sạch
              </span>
            </div>

            {loadingListings ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div
                    key={i}
                    className="h-80 bg-white dark:bg-slate-900 rounded-[20px] border border-[#E7E2DA] dark:border-slate-800 animate-pulse"
                  />
                ))}
              </div>
            ) : listings.length === 0 ? (
              <div className="bg-white dark:bg-slate-900 rounded-[20px] border border-[#E7E2DA] dark:border-slate-800 p-12 text-center flex flex-col items-center shadow-sm">
                <div className="w-14 h-14 rounded-2xl bg-[#0F5F58]/10 text-[#0F5F58] flex items-center justify-center mb-3">
                  <Inbox className="w-7 h-7" />
                </div>
                <h3 className="font-bold text-base text-[#111827] dark:text-white mb-1 font-display">
                  Không tìm thấy tin phòng phù hợp
                </h3>
                <p className="text-xs text-[#6B7280] max-w-sm mb-4 leading-relaxed">
                  Hãy thử nới lỏng khoảng giá, giảm bớt từ khóa hoặc chọn toàn TP.HCM để xem nhiều kết quả hơn.
                </p>
                <button
                  type="button"
                  onClick={handleResetFilters}
                  className="px-5 py-2.5 bg-[#0F5F58] text-white rounded-full text-xs font-semibold hover:bg-[#004640] transition-colors shadow-sm cursor-pointer"
                >
                  Xoá các bộ lọc
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                {listings.map((item) => (
                  <ListingCard
                    key={item.id}
                    listing={item}
                    marketPrice={marketCard?.price}
                  />
                ))}
              </div>
            )}

            <Pagination
              meta={listingsRes?.meta?.pagination}
              onPageChange={(p) => updateParam("page", p)}
            />

            <p className="text-xs text-[#9CA3AF] text-center max-w-md mx-auto pt-4 leading-relaxed font-sans">
              Dữ liệu được làm sạch loại bỏ tin ảo và trùng lặp bởi thuật toán RoomBeacon AI. Cập nhật liên tục từ các nguồn tin thực tế.
            </p>
          </div>

          {/* Right Column: District Market Intelligence (col-span-12 lg:col-span-3) */}
          <aside className="col-span-12 lg:col-span-3 sticky top-24 space-y-6">
            <MarketPriceBadge
              locationName={marketLocationName}
              cardData={marketCard}
            />
          </aside>
        </div>
      </main>

      {/* Mobile Filter Sheet */}
      {mobileFilterOpen && (
        <div className="fixed inset-0 z-50 flex flex-col justify-end bg-black/50 backdrop-blur-sm lg:hidden animate-fade-in">
          <div
            className="w-full bg-white dark:bg-[#1A2234] rounded-t-[28px] border-t border-[#E7E2DA] dark:border-slate-800 shadow-2xl p-5 max-h-[85vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-3 border-b border-[#E7E2DA] dark:border-slate-800 mb-4">
              <h3 className="font-bold text-base text-[#111827] dark:text-white font-display">
                Bộ lọc tìm kiếm
              </h3>
              <button
                type="button"
                onClick={() => setMobileFilterOpen(false)}
                className="p-1.5 text-[#6B7280] hover:text-[#111827] rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <FilterSidebar
              priceMin={priceMin}
              priceMax={priceMax}
              areaMin={areaMin}
              areaMax={areaMax}
              sort={sort}
              onPriceChange={handlePriceChange}
              onAreaChange={handleAreaChange}
              onSortChange={(val) => updateParam("sort", val)}
              onReset={handleResetFilters}
            />
            <button
              type="button"
              onClick={() => setMobileFilterOpen(false)}
              className="w-full mt-4 py-3 bg-[#B8892E] text-white font-bold rounded-full text-sm shadow-md cursor-pointer"
            >
              Xem kết quả
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
