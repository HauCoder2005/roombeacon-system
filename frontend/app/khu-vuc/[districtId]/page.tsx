import React from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  getServerDistrict,
  getServerDistrictWards,
  getServerMarketSummary,
  getServerMarketDaily,
  getServerListings,
} from "@/lib/api/server";
import { PriceRangeStrip } from "@/components/cards/PriceRangeStrip";
import { DistrictWardsList } from "@/components/cards/DistrictWardsList";
import { ListingCard } from "@/components/cards/ListingCard";
import { MarketTrendChart } from "@/components/charts/MarketTrendChart";
import {
  formatListingCount,
  formatPrice,
  formatPricePerM2,
  formatArea,
  formatNumber,
} from "@/lib/format";
import { MapPin, ChevronLeft, ArrowRight, Gauge, TrendingUp, Search } from "lucide-react";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ districtId: string }>;
}): Promise<Metadata> {
  const { districtId } = await params;
  try {
    const res = await getServerDistrict(districtId);
    const district = res?.data;
    if (!district) return notFound();

    const priceText = formatPrice(district.price.median, { perMonth: true });
    return {
      title: `Giá thuê phòng trọ ${district.name} — RoomBeacon`,
      description: `Thống kê giá thuê phòng trọ, căn hộ tại ${district.name}: giá trung vị ${priceText}, diện tích TB ${formatArea(
        district.price.median_area_m2
      )}, tổng hợp từ ${formatListingCount(district.stats.listing_count)}.`,
    };
  } catch {
    return notFound();
  }
}

export default async function DistrictDetailPage({
  params,
}: {
  params: Promise<{ districtId: string }>;
}) {
  const { districtId } = await params;

  let district = null;
  let wards = [];
  let marketSummary = null;
  let dailyTrends = [];
  let recentListings = [];

  try {
    const [
      districtRes,
      wardsRes,
      summaryRes,
      dailyRes,
      listingsRes,
    ] = await Promise.all([
      getServerDistrict(districtId),
      getServerDistrictWards(districtId, {
        per_page: 50,
        sort: "-listing_count",
      }),
      getServerMarketSummary(districtId).catch(() => ({ data: null })),
      getServerMarketDaily(districtId, "2026-09-23").catch(() => ({ data: [] })),
      getServerListings({ district_id: districtId, per_page: 8 }).catch(() => ({
        data: [],
      })),
    ]);

    district = districtRes.data;
    wards = wardsRes.data || [];
    marketSummary = summaryRes.data;
    dailyTrends = dailyRes.data || [];
    recentListings = listingsRes.data || [];
  } catch {
    notFound();
  }

  if (!district) {
    notFound();
  }

  const listingCount =
    marketSummary?.listing_count ?? district.stats.listing_count;

  return (
    <div className="min-h-screen bg-[#FAF8F5] dark:bg-slate-950 pb-20 font-sans">
      {/* SECTION 1: DARK EDITORIAL URBAN DATA HEADER */}
      <section className="relative w-full bg-[#0F5F58] text-white pt-12 pb-16 px-6 md:px-12 overflow-hidden shadow-lg">
        {/* Ambient Radial Lighting */}
        <div className="absolute -right-20 -top-20 w-[500px] h-[500px] bg-[#B8892E]/20 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -left-20 -bottom-20 w-[400px] h-[400px] bg-white/5 rounded-full blur-2xl pointer-events-none" />

        <div className="max-w-[1320px] mx-auto relative z-10 space-y-8">
          {/* Back breadcrumb */}
          <div>
            <Link
              href="/khu-vuc"
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-white/70 hover:text-white transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
              <span>Tất cả khu vực TP.HCM</span>
            </Link>
          </div>

          {/* District Title & Subtitle */}
          <div className="max-w-3xl space-y-2">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/10 backdrop-blur-md text-white text-xs font-semibold uppercase tracking-wider">
              <MapPin className="w-3.5 h-3.5 text-[#FCC665]" />
              <span>Báo cáo dữ liệu thị trường</span>
            </div>
            <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-medium tracking-tight text-white">
              {district.name}
            </h1>
            <p className="text-sm sm:text-base text-white/80 leading-relaxed font-sans">
              Bao gồm {district.stats.ward_count} phường trực thuộc · Tổng hợp dữ liệu chuẩn hóa từ {formatListingCount(listingCount)} tin đăng
            </p>
          </div>

          {/* 4 Frosted Glass Stat Boxes */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 items-stretch pt-4">
            <div className="p-6 rounded-2xl bg-white/10 backdrop-blur-md border border-white/20 flex flex-col justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-white/70 block">
                Tổng số tin
              </span>
              <div className="my-2 flex items-baseline gap-2">
                <span className="font-display text-3xl sm:text-4xl font-bold text-white">
                  {formatNumber(listingCount)}
                </span>
              </div>
              <p className="text-xs text-white/60">Tin đăng RoomBeacon ghi nhận trong khu vực</p>
            </div>

            <div className="p-6 rounded-2xl bg-white/10 backdrop-blur-md border border-white/20 flex flex-col justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-white/70 block">
                Giá thuê trung vị
              </span>
              <div className="my-2">
                <span className="font-display text-3xl sm:text-4xl font-bold text-white">
                  {formatPrice(district.price.median, { perMonth: false, shortUnit: false })}
                </span>
                <span className="text-xs text-white/70 ml-1">/ tháng</span>
              </div>
              <p className="text-xs text-white/60">Mức chi trả phổ biến nhất</p>
            </div>

            <div className="p-6 rounded-2xl bg-white/10 backdrop-blur-md border border-white/20 flex flex-col justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-white/70 block">
                Dải giá phổ biến (p25 – p75)
              </span>
              <div className="my-2">
                <span className="font-display text-2xl sm:text-3xl font-bold text-[#FCC665]">
                  {formatPrice(district.price.p25, { shortUnit: true })} – {formatPrice(district.price.p75, { shortUnit: true })}
                </span>
              </div>
              <p className="text-xs text-white/60">Một nửa số tin nằm trong dải này</p>
            </div>

            {/* Action buttons box */}
            <div className="flex flex-col gap-3 justify-center">
              <Link
                href={`/tim-phong?district_id=${district.id}`}
                className="w-full h-12 rounded-full bg-[#B8892E] hover:bg-[#a07424] text-white font-semibold text-xs transition-all shadow-md flex items-center justify-center gap-2 cursor-pointer"
              >
                <span>Tìm phòng tại {district.name}</span>
                <Search className="w-4 h-4 stroke-[2.5]" />
              </Link>
              <Link
                href={`/dinh-gia?district_id=${district.id}`}
                className="w-full h-12 rounded-full bg-white/15 hover:bg-white/25 backdrop-blur-md text-white font-semibold text-xs transition-all flex items-center justify-center gap-2 cursor-pointer"
              >
                <span>Định giá phòng tại {district.name}</span>
                <Gauge className="w-4 h-4" />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* SECTION 2: CONTENT WORKSPACE */}
      <main className="max-w-[1320px] mx-auto px-6 md:px-12 py-14 space-y-16">
        {/* Market Trend Chart */}
        {dailyTrends.length > 0 && (
          <MarketTrendChart days={dailyTrends} districtName={district.name} />
        )}

        {/* District Wards List */}
        <DistrictWardsList initialWards={wards} />

        {/* Recent listings in district */}
        {recentListings.length > 0 && (
          <div className="space-y-6 pt-4 border-t border-[#E7E2DA] dark:border-slate-800">
            <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
              <div>
                <span className="text-[11px] uppercase tracking-widest text-[#0F5F58] dark:text-[#91D6CD] font-semibold block mb-1">
                  Nguồn tin mới nhất
                </span>
                <h3 className="font-display text-2xl sm:text-3xl font-medium text-[#111827] dark:text-white">
                  Phòng đang cho thuê tại {district.name}
                </h3>
              </div>
              <Link
                href={`/tim-phong?district_id=${district.id}`}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#0F5F58] dark:text-[#91D6CD] hover:underline"
              >
                <span>Xem tất cả tin {district.name}</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
              {recentListings.map((item) => (
                <ListingCard
                  key={item.id}
                  listing={item}
                  marketPrice={district.price}
                />
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
