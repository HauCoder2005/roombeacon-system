import React from "react";
import Link from "next/link";
import { getServerDistricts, getServerListings } from "@/lib/api/server";
import { SearchBar } from "@/components/search/SearchBar";
import { DistrictCard } from "@/components/cards/DistrictCard";
import { ListingCard } from "@/components/cards/ListingCard";
import { MarketPriceTable } from "@/components/home/MarketPriceTable";
import { QuickEstimateBox } from "@/components/home/QuickEstimateBox";
import { WhyRoomBeacon } from "@/components/home/WhyRoomBeacon";
import { formatNumber, formatVietnamDateTime } from "@/lib/format";
import { ArrowRight } from "lucide-react";

export default async function HomePage() {
  let districtsData = null;
  let listingsData = null;

  try {
    const [districtsRes, listingsRes] = await Promise.all([
      getServerDistricts({ per_page: 55, sort: "-listing_count" }),
      getServerListings({ per_page: 8, sort: "-last_observed_at" }),
    ]);
    districtsData = districtsRes;
    listingsData = listingsRes;
  } catch {
    // Graceful fallback if backend temporarily unreachable
  }

  const districts = districtsData?.data || [];
  const listings = listingsData?.data || [];
  const top8Districts = districts.slice(0, 8);

  const totalListings = listingsData?.meta?.pagination?.total_items || 76531;
  const totalDistricts = districtsData?.meta?.pagination?.total_items || 55;
  const snapshotDate = districtsData?.meta?.data_snapshot?.loaded_at;

  return (
    <div className="flex flex-col min-h-screen">
      {/* SECTION 1: EDITORIAL HERO & ARCHITECTURAL SEARCH BAR */}
      <section className="relative w-full pt-16 pb-20 px-6 md:px-12 bg-[#FAF8F5] dark:bg-slate-950 overflow-hidden border-b border-[#E7E2DA] dark:border-slate-800">
        {/* Soft Ambient Backdrop Glows */}
        <div className="absolute top-12 left-1/2 -translate-x-1/2 w-[1100px] h-[360px] bg-gradient-to-b from-[#A9F0E6]/30 via-slate-100/20 to-transparent blur-3xl pointer-events-none rounded-full -z-10" />

        <div className="max-w-[1320px] mx-auto flex flex-col items-center text-center">
          {/* Real-time indicator pill */}
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white dark:bg-slate-900 border border-[#E7E2DA] dark:border-slate-800 text-[#0F5F58] dark:text-[#91D6CD] text-xs font-semibold uppercase tracking-wider mb-5 shadow-xs">
            <span className="w-2 h-2 rounded-full bg-[#B8892E] animate-pulse" />
            <span>Dữ liệu giá thuê · TP.HCM</span>
          </div>

          {/* Hero Headline */}
          <h1 className="font-display text-4xl sm:text-5xl lg:text-[54px] font-medium text-[#111827] dark:text-white tracking-tight leading-[1.15] max-w-4xl mb-4">
            Tìm phòng trọ ở TP.HCM — biết rõ giá trước khi hỏi
          </h1>

          {/* Hero Subtitle with accurate total metrics */}
          <p className="text-sm sm:text-base text-[#6B7280] dark:text-slate-400 font-sans tracking-wide max-w-2xl mb-10">
            {formatNumber(totalListings)} tin đăng đã làm sạch{" "}
            <span className="mx-1.5 opacity-40">·</span> {totalDistricts} quận/khu vực{" "}
            <span className="mx-1.5 opacity-40">·</span> Cập nhật{" "}
            {formatVietnamDateTime(snapshotDate)}
          </p>

          {/* Centerpiece Architectural Search Bar */}
          <SearchBar showQuickChips={true} />
        </div>
      </section>

      {/* SECTION 2: KHÁM PHÁ THEO KHU VỰC (4x2 Grid) */}
      <section className="bg-white dark:bg-[#151D2C] py-20 px-6 md:px-12">
        <div className="max-w-[1320px] mx-auto">
          <div className="flex flex-col md:flex-row md:items-end justify-between mb-12 gap-4">
            <div>
              <span className="text-[11px] uppercase tracking-widest text-[#0F5F58] dark:text-[#91D6CD] font-semibold block mb-2">
                Bản đồ giá thị trường
              </span>
              <h2 className="text-3xl sm:text-4xl font-display font-medium text-[#111827] dark:text-white tracking-tight">
                Khám phá theo khu vực
              </h2>
              <p className="text-sm text-[#6B7280] dark:text-slate-400 mt-1.5 font-sans">
                Phân tích giá thuê theo quận/huyện dựa trên tin đăng cho thuê đã làm sạch
              </p>
            </div>
            <Link
              href="/khu-vuc"
              className="inline-flex items-center gap-2 text-sm font-semibold text-[#0F5F58] dark:text-[#91D6CD] pb-1 border-b border-[#0F5F58]/30 hover:border-[#0F5F58] transition group"
            >
              <span>Xem tất cả {totalDistricts} khu vực</span>
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </Link>
          </div>

          {/* 4x2 Grid of District Cards */}
          {/* Mobile: horizontal swipe row (design: trang chủ mobile); desktop: 4x2 grid */}
          <div className="-mx-5 flex snap-x snap-mandatory gap-4 overflow-x-auto px-5 pb-2 [scrollbar-width:none] sm:mx-0 sm:grid sm:grid-cols-2 sm:gap-6 sm:overflow-visible sm:px-0 sm:pb-0 lg:grid-cols-4">
            {top8Districts.map((card) => (
              <DistrictCard key={card.id} card={card} className="w-[78%] shrink-0 snap-start sm:w-auto" />
            ))}
          </div>
        </div>
      </section>

      {/* SECTION 3: BẢNG GIÁ THUÊ THEO KHU VỰC (Comparison Table) */}
      <MarketPriceTable />

      {/* SECTION 4: TIN MỚI CẬP NHẬT (Verified Listing Cards) */}
      <section className="bg-white dark:bg-[#151D2C] py-20 px-6 md:px-12 border-b border-[#E7E2DA] dark:border-slate-800">
        <div className="max-w-[1320px] mx-auto">
          <div className="flex flex-col md:flex-row md:items-end justify-between mb-12 gap-4">
            <div>
              <span className="text-[11px] uppercase tracking-widest text-[#0F5F58] dark:text-[#91D6CD] font-semibold block mb-2">
                Nguồn cung trực tiếp
              </span>
              <h2 className="text-3xl sm:text-4xl font-display font-medium text-[#111827] dark:text-white tracking-tight">
                Tin mới cập nhật
              </h2>
              <p className="text-sm text-[#6B7280] dark:text-slate-400 mt-1.5 font-sans">
                Tin cho thuê RoomBeacon vừa ghi nhận, kèm vị trí giá so với khu vực
              </p>
            </div>
            <Link
              href="/tim-phong"
              className="inline-flex items-center gap-2 text-sm font-semibold text-[#0F5F58] dark:text-[#91D6CD] pb-1 border-b border-[#0F5F58]/30 hover:border-[#0F5F58] transition group"
            >
              <span>Xem thêm tin mới</span>
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </Link>
          </div>

          {/* 4 or 8 Listing Cards Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {listings.map((listing) => {
              const matchingDistrict = districts.find(
                (d) => d.id === listing.location?.district?.id
              );
              return (
                <ListingCard
                  key={listing.id}
                  listing={listing}
                  marketPrice={matchingDistrict?.price}
                />
              );
            })}
          </div>
        </div>
      </section>

      {/* SECTION 5: BAND ĐỊNH GIÁ TRONG 10 GIÂY */}
      {top8Districts.length > 0 && <QuickEstimateBox districts={top8Districts} />}

      {/* SECTION 6: TRIẾT LÝ & VÌ SAO CHỌN ROOMBEACON */}
      <WhyRoomBeacon />
    </div>
  );
}
