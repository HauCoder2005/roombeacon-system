import { safeExternalUrl } from "@/lib/safeUrl";
import { trustworthyValuation } from "@/lib/valuation";
import React from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  getServerListing,
  getServerListingPriceHistory,
  getServerListingImages,
  getServerListings,
} from "@/lib/api/server";
import {
  formatPrice,
  formatArea,
  formatPricePerM2,
  formatVietnamDateTime,
  formatRelativeTime,
} from "@/lib/format";
import { PriceRangeStrip } from "@/components/cards/PriceRangeStrip";
import { ValuationBadge } from "@/components/cards/ValuationBadge";
import { ListingCard } from "@/components/cards/ListingCard";
import { ListingGallery } from "@/components/listing/ListingGallery";
import { ListingActionBar } from "@/components/listing/ListingActionBar";
import { PriceHistoryChart } from "@/components/charts/PriceHistoryChart";
import {
  MapPin,
  Clock,
  Sparkles,
  TrendingDown,
  TrendingUp,
  ShieldCheck,
  Building,
  Key,
  Compass,
  Square,
  CheckCircle2,
  WashingMachine,
  ArrowRight,
} from "lucide-react";

interface ListingPageProps {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({
  params,
}: ListingPageProps): Promise<Metadata> {
  const { id } = await params;
  try {
    const res = await getServerListing(id);
    const listing = res?.data;
    if (!listing) return notFound();

    const priceText = formatPrice(listing.price?.amount, { perMonth: true });
    const locationText = [
      listing.location?.ward?.name,
      listing.location?.district?.name,
    ]
      .filter(Boolean)
      .join(", ");

    return {
      title: `${listing.title} — RoomBeacon`,
      description: `Thuê phòng trọ: ${priceText}, diện tích ${formatArea(
        listing.area_m2
      )} tại ${locationText}. Dữ liệu giá thị trường minh bạch và định giá tham khảo tại RoomBeacon.`,
    };
  } catch {
    return notFound();
  }
}

export default async function ListingDetailPage({ params }: ListingPageProps) {
  const { id } = await params;

  let listing = null;
  let historyPoints = [];
  let fetchedImages: any[] = [];
  try {
    const [detailRes, historyRes, imagesRes] = await Promise.all([
      getServerListing(id),
      getServerListingPriceHistory(id),
      getServerListingImages(id),
    ]);
    listing = detailRes.data;
    historyPoints = historyRes.data || [];
    fetchedImages = imagesRes?.data || [];
  } catch (err) {
    notFound();
  }

  if (!listing) {
    notFound();
  }

  const galleryImages =
    fetchedImages.length > 0
      ? fetchedImages
      : (listing.images?.preview || []).map((url: string, idx: number) => ({
          position: idx + 1,
          url,
        }));

  const priceAmount = listing.price?.amount ?? null;
  const valuation = trustworthyValuation(listing);
  const district = listing.location?.district;
  const ward = listing.location?.ward;
  const locationText = [ward?.name, district?.name].filter(Boolean).join(", ");

  // Fetch similar listings around ±20% price in same ward or district
  let similarListings: any[] = [];
  try {
    const priceMin = priceAmount ? Math.round(priceAmount * 0.8) : undefined;
    const priceMax = priceAmount ? Math.round(priceAmount * 1.2) : undefined;
    const similarRes = await getServerListings({
      ward_id: ward?.id || undefined,
      district_id: district?.id || undefined,
      price_min: priceMin,
      price_max: priceMax,
      per_page: 5,
    });
    if (similarRes.data) {
      similarListings = similarRes.data
        .filter((l) => l.id !== listing.id)
        .slice(0, 3);
    }
  } catch {
    // ignore similar listing error
  }

  const marketPriceObj = listing.market
    ? {
        currency: "VND" as const,
        median: listing.market.median,
        p25: listing.market.p25,
        p75: listing.market.p75,
        median_per_m2: null,
        median_area_m2: null,
      }
    : null;

  return (
    <div className="min-h-screen bg-[#FAF8F5] dark:bg-slate-950 py-8 px-6 md:px-12 font-sans">
      <div className="max-w-[1320px] mx-auto space-y-8">
        {/* Top Breadcrumb Navigation */}
        <nav className="flex items-center gap-2 text-xs text-[#6B7280] dark:text-slate-400">
          <Link href="/" className="hover:text-[#0F5F58] transition-colors">
            Trang chủ
          </Link>
          <span>/</span>
          <Link href="/tim-phong" className="hover:text-[#0F5F58] transition-colors">
            TP. Hồ Chí Minh
          </Link>
          {district && (
            <>
              <span>/</span>
              <Link href={`/khu-vuc/${district.id}`} className="hover:text-[#0F5F58] transition-colors">
                {district.name}
              </Link>
            </>
          )}
          {ward && (
            <>
              <span>/</span>
              <span className="text-[#111827] dark:text-white font-medium">{ward.name}</span>
            </>
          )}
          <span>/</span>
          <span className="text-[#0F5F58] dark:text-[#91D6CD] font-semibold truncate max-w-[160px]">
            Tin #{listing.id}
          </span>
        </nav>

        {/* Editorial Top Headline Banner */}
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="px-2.5 py-1 rounded-full bg-[#0F5F58]/10 text-[#0F5F58] dark:text-[#91D6CD] font-semibold uppercase tracking-wider">
              Nguồn: {listing.source}
            </span>
            {valuation && (
              <ValuationBadge valuation={valuation} />
            )}
            <span className="text-[#6B7280] dark:text-slate-400 ml-auto hidden sm:inline">
              Cập nhật thực địa: {formatRelativeTime(listing.last_observed_at)}
            </span>
          </div>

          <h1 className="font-display text-3xl sm:text-4xl lg:text-[40px] font-medium text-[#111827] dark:text-white tracking-tight leading-snug">
            {listing.title}
          </h1>

          <div className="flex items-center gap-1.5 text-sm text-[#6B7280] dark:text-slate-400">
            <MapPin className="w-4 h-4 text-[#0F5F58] shrink-0" />
            <span>{locationText || "TP. Hồ Chí Minh"}</span>
            {district && (
              <Link
                href={`/khu-vuc/${district.id}`}
                className="text-xs text-[#0F5F58] dark:text-[#91D6CD] hover:underline font-semibold ml-2"
              >
                (Xem thị trường {district.name} →)
              </Link>
            )}
          </div>
        </div>

        {/* Main 2-Column Architectural Workspace */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* LEFT COLUMN (Approx 68% -> lg:col-span-8) */}
          <div className="lg:col-span-8 flex flex-col gap-8">
            {/* Visual Media Gallery */}
            <ListingGallery
              images={galleryImages}
              title={listing.title}
              source={listing.source}
            />

            {/* Key facts — only fields the listing API returns */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="flex flex-col gap-1 rounded-2xl border border-border bg-surface p-4">
                <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
                  <Square className="h-4 w-4 text-brand" strokeWidth={1.6} aria-hidden />
                  Diện tích
                </span>
                <span className="mt-1 font-display text-2xl font-medium text-ink">{formatArea(listing.area_m2)}</span>
                <span className="text-xs text-ink-muted">Theo tin đăng</span>
              </div>
              <div className="flex flex-col gap-1 rounded-2xl border border-border bg-surface p-4">
                <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
                  <Compass className="h-4 w-4 text-brand" strokeWidth={1.6} aria-hidden />
                  Đơn giá / m²
                </span>
                <span className="mt-1 font-display text-2xl font-medium text-ink">{formatPricePerM2(listing.price_per_m2)}</span>
                <span className="text-xs text-ink-muted">Giá thuê / diện tích</span>
              </div>
              <div className="flex flex-col gap-1 rounded-2xl border border-border bg-surface p-4">
                <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
                  <Building className="h-4 w-4 text-brand" strokeWidth={1.6} aria-hidden />
                  Hoạt động
                </span>
                <span className="mt-1 font-display text-2xl font-medium text-ink">{listing.active_days != null ? `${listing.active_days} ngày` : "Chưa rõ"}</span>
                <span className="text-xs text-ink-muted">Từ lần ghi nhận đầu</span>
              </div>
              <div className="flex flex-col gap-1 rounded-2xl border border-border bg-surface p-4">
                <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
                  <Key className="h-4 w-4 text-brand" strokeWidth={1.6} aria-hidden />
                  Nguồn
                </span>
                <span className="mt-1 font-display text-2xl font-medium text-ink">{listing.source}</span>
                <span className="text-xs text-ink-muted">Trang đăng tin gốc</span>
              </div>
            </div>

            {/* Listing facts table */}
            <section className="rounded-2xl border border-border bg-surface p-6 md:p-8">
              <h2 className="font-display text-xl font-medium text-ink">Thông tin tin đăng</h2>
              <p className="mt-1 text-xs text-ink-muted">Dữ liệu RoomBeacon ghi nhận từ tin đăng công khai; không bao gồm thông tin liên hệ người đăng.</p>
              <dl className="mt-5 grid grid-cols-1 gap-x-8 gap-y-4 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-muted">Khu vực</dt>
                  <dd className="mt-0.5 text-ink">{locationText || "Chưa xác định"}</dd>
                </div>
                <div>
                  <dt className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-muted">Mã tin RoomBeacon</dt>
                  <dd className="mt-0.5 font-mono text-[13px] text-ink">#{listing.id}</dd>
                </div>
                <div>
                  <dt className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-muted">Ghi nhận lần đầu</dt>
                  <dd className="mt-0.5 text-ink">{formatVietnamDateTime(listing.first_observed_at)}</dd>
                </div>
                <div>
                  <dt className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-muted">Cập nhật gần nhất</dt>
                  <dd className="mt-0.5 text-ink">{formatVietnamDateTime(listing.last_observed_at)}</dd>
                </div>
                <div>
                  <dt className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-muted">Giá niêm yết</dt>
                  <dd className="mt-0.5 font-semibold text-ink">{formatPrice(priceAmount)}/tháng</dd>
                </div>
                <div>
                  <dt className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-muted">Trùng lặp</dt>
                  <dd className="mt-0.5 text-ink">{listing.quality.duplicate_status === "POSSIBLE_DUPLICATE" ? "Có thể trùng tin khác" : "Không phát hiện trùng"}</dd>
                </div>
              </dl>
            </section>

            {/* Price History Step Chart */}
            <PriceHistoryChart points={historyPoints} />
          </div>

          {/* RIGHT COLUMN: Sticky Price & Valuation Card (Approx 32% -> lg:col-span-4) */}
          <aside className="lg:col-span-4 sticky top-24 space-y-6">
            <div className="bg-white dark:bg-[#1A2234] rounded-[24px] p-6 sm:p-7 border border-[#E7E2DA] dark:border-slate-800 shadow-md space-y-6">
              {/* Valuation difference pill */}
              {valuation && (
                <div className="flex items-center justify-between">
                  <span
                    className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold ${
                      valuation.label === "BELOW_ESTIMATE"
                        ? "bg-[#ECFDF5] text-[#047857]"
                        : valuation.label === "ABOVE_ESTIMATE"
                        ? "bg-[#FEF2F2] text-[#B91C1C]"
                        : "bg-[#FAF8F5] text-[#0F5F58]"
                    }`}
                  >
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>
                      {valuation.label === "BELOW_ESTIMATE"
                        ? `Rẻ hơn ${Math.abs(Math.round(valuation.delta_pct))}% so với mô hình AI`
                        : valuation.label === "ABOVE_ESTIMATE"
                        ? `Cao hơn ${Math.round(valuation.delta_pct)}% so với mô hình AI`
                        : "Sát với giá ước tính mô hình AI"}
                    </span>
                  </span>
                </div>
              )}

              {/* Price hero */}
              <div>
                <span className="text-[11px] uppercase tracking-wider text-[#6B7280] dark:text-slate-400 font-semibold block mb-1">
                  Giá thuê niêm yết
                </span>
                <div className="text-3xl sm:text-[34px] font-bold text-[#111827] dark:text-white font-sans tracking-tight">
                  {formatPrice(priceAmount, { perMonth: false })}
                  <span className="text-sm font-normal text-[#6B7280] ml-1.5">/ tháng</span>
                </div>
                <div className="text-xs text-[#6B7280] dark:text-slate-400 mt-1">
                  Đơn giá {formatPricePerM2(listing.price_per_m2)} · {formatArea(listing.area_m2)}
                </div>
              </div>

              {/* Sub-district price strip */}
              {marketPriceObj && (
                <div className="space-y-2 pt-4 border-t border-[#E7E2DA] dark:border-slate-800">
                  <div className="flex justify-between items-center text-xs text-[#6B7280] dark:text-slate-400 font-semibold">
                    <span>Phổ giá: {ward?.name || district?.name || "Khu vực"}</span>
                    <span className="text-[#0F5F58] dark:text-[#91D6CD]">
                      Trung vị: {formatPrice(marketPriceObj.median, { shortUnit: true })}
                    </span>
                  </div>
                  <PriceRangeStrip
                    price={marketPriceObj}
                    currentPrice={priceAmount}
                    size="md"
                    showLabels={true}
                  />
                </div>
              )}

              {/* Transaction Action Buttons */}
              <ListingActionBar
                sourceUrl={safeExternalUrl(listing.source_url)}
                sourceName={listing.source}
                listingId={listing.id}
              />

              {/* Strict Trust Note */}
              <div className="pt-4 border-t border-[#E7E2DA] dark:border-slate-800 flex items-start gap-2.5 text-[#6B7280] dark:text-slate-400">
                <ShieldCheck className="w-4 h-4 text-[#0F5F58] shrink-0 mt-0.5" />
                <p className="text-xs leading-relaxed font-sans">
                  <strong className="font-semibold text-ink">Lưu ý:</strong>{" "}
                  RoomBeacon tổng hợp tin đăng công khai và không phải bên cho thuê. Hãy xác minh giá, chi phí và điều khoản trực tiếp với người đăng trước khi đặt cọc.
                </p>
              </div>
            </div>
          </aside>
        </div>

        {/* BOTTOM SECTION: Tin Tương Tự Trong Khu Vực */}
        {similarListings.length > 0 && (
          <section className="pt-12 border-t border-[#E7E2DA] dark:border-slate-800">
            <div className="flex flex-col sm:flex-row sm:items-end justify-between mb-8 gap-3">
              <div>
                <span className="text-[11px] uppercase tracking-widest text-[#0F5F58] dark:text-[#91D6CD] font-semibold block mb-1">
                  Gợi ý tuyển chọn
                </span>
                <h2 className="font-display text-2xl sm:text-3xl font-medium text-[#111827] dark:text-white">
                  Phòng tương tự tại {locationText || "khu vực"}
                </h2>
              </div>
              {district && (
                <Link
                  href={`/tim-phong?district_id=${district.id}`}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#0F5F58] dark:text-[#91D6CD] hover:underline"
                >
                  <span>Xem thêm phòng tại {district.name}</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {similarListings.map((sim) => (
                <ListingCard
                  key={sim.id}
                  listing={sim}
                  marketPrice={marketPriceObj}
                />
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
