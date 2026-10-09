"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useDistricts } from "@/lib/api/hooks";
import { formatPrice, formatPricePerM2, formatListingCount } from "@/lib/format";
import { PriceRangeStrip } from "../cards/PriceRangeStrip";
import { Search } from "lucide-react";

const MIN_PRICED_LISTINGS = 200;
const DEFAULT_ROWS = 10;

export const MarketPriceTable: React.FC = () => {
  const [metric, setMetric] = useState<"month" | "m2">("month");
  const [searchDistrict, setSearchDistrict] = useState("");
  const [expanded, setExpanded] = useState(false);

  const { data, isLoading } = useDistricts({
    per_page: 55,
    sort: "-median_price",
  });

  const districts = data?.data || [];
  // Areas with few priced listings give unstable medians (and include parser noise
  // from outside TP.HCM), so the comparison table only ranks well-sampled areas.
  const filtered = districts.filter(
    (d) =>
      d.stats.priced_listing_count >= MIN_PRICED_LISTINGS &&
      d.name.toLowerCase().includes(searchDistrict.toLowerCase().trim())
  );
  const visible = expanded || searchDistrict.trim() ? filtered : filtered.slice(0, DEFAULT_ROWS);

  return (
    <section id="bang-gia" className="bg-[#FAF8F5] dark:bg-slate-900/60 py-20 px-6 md:px-12 border-y border-[#E7E2DA] dark:border-slate-800">
      <div className="max-w-[1320px] mx-auto">
        {/* Section Header */}
        <div className="flex flex-col sm:flex-row sm:items-end justify-between mb-10 gap-4">
          <div>
            <span className="text-[11px] uppercase tracking-widest text-[#0F5F58] dark:text-[#91D6CD] font-semibold block mb-2">
              Chỉ số so sánh liên quận
            </span>
            <h2 className="text-3xl sm:text-4xl font-display font-medium text-[#111827] dark:text-white tracking-tight">
              Bảng giá thuê theo khu vực
            </h2>
            <p className="text-sm text-[#6B7280] dark:text-slate-400 mt-1.5 font-sans">
              Chuẩn hóa theo phân vị 25% – 75% giúp loại bỏ các tin đăng giá ảo
            </p>
          </div>

          <div className="flex items-center gap-3 self-start sm:self-auto flex-wrap">
            {/* Search Filter input */}
            <div className="relative flex items-center">
              <Search className="w-3.5 h-3.5 text-[#6B7280] absolute left-3 pointer-events-none" />
              <input
                type="text"
                value={searchDistrict}
                onChange={(e) => setSearchDistrict(e.target.value)}
                placeholder="Lọc tên quận…"
                className="pl-8 pr-3 py-2 text-xs rounded-full bg-white dark:bg-slate-800 border border-[#E7E2DA] dark:border-slate-700 text-[#111827] dark:text-white focus:outline-none focus:border-[#0F5F58] w-36 sm:w-44 transition-all"
              />
            </div>

            {/* Mode Toggle Switch */}
            <div className="inline-flex p-1 bg-white dark:bg-slate-800 border border-[#E7E2DA] dark:border-slate-700 rounded-full shadow-sm">
              <button
                type="button"
                onClick={() => setMetric("month")}
                className={`px-5 py-2 rounded-full text-xs font-semibold transition-all ${
                  metric === "month"
                    ? "bg-[#0F5F58] text-white shadow-sm"
                    : "text-[#6B7280] dark:text-slate-400 hover:text-[#111827] dark:hover:text-white"
                }`}
              >
                Theo tháng
              </button>
              <button
                type="button"
                onClick={() => setMetric("m2")}
                className={`px-5 py-2 rounded-full text-xs font-semibold transition-all ${
                  metric === "m2"
                    ? "bg-[#0F5F58] text-white shadow-sm"
                    : "text-[#6B7280] dark:text-slate-400 hover:text-[#111827] dark:hover:text-white"
                }`}
              >
                Theo m²
              </button>
            </div>
          </div>
        </div>

        {/* Quantitative Comparison Table */}
        <div className="bg-white dark:bg-[#1A2234] rounded-[20px] border border-[#E7E2DA] dark:border-slate-800 shadow-[0_10px_30px_rgba(17,24,39,0.03)] overflow-hidden">
          {/* Table Header */}
          <div className="hidden md:grid grid-cols-12 px-6 py-4 bg-[#FAF8F5]/80 dark:bg-slate-900/60 border-b border-[#E7E2DA] dark:border-slate-800 text-[#6B7280] dark:text-slate-400 text-[11px] uppercase tracking-wider font-semibold">
            <div className="col-span-3">Khu vực / Quy mô</div>
            <div className="col-span-5 text-center">Phổ giá thực tế (p25 – Trung vị – p75)</div>
            <div className="col-span-2 text-right">Giá trung vị</div>
            <div className="col-span-2 text-right">Mẫu tính giá</div>
          </div>

          {/* Table Rows */}
          <div className="divide-y divide-[#E7E2DA]/60 dark:divide-slate-800">
            {isLoading ? (
              <div className="p-12 text-center text-sm text-[#6B7280]">
                Đang tổng hợp dữ liệu chuẩn hóa các khu vực…
              </div>
            ) : filtered.length === 0 ? (
              <div className="p-12 text-center text-sm text-[#6B7280]">
                Không tìm thấy khu vực phù hợp.
              </div>
            ) : (
              visible.map((d) => (
                <div
                  key={d.id}
                  className="grid grid-cols-1 md:grid-cols-12 px-6 py-4 md:py-5 items-center hover:bg-[#FAF8F5]/50 dark:hover:bg-slate-800/40 transition group gap-3 md:gap-0"
                >
                  {/* District / Scale */}
                  <div className="col-span-3">
                    <Link
                      href={`/khu-vuc/${d.id}`}
                      className="font-semibold text-[16px] text-[#111827] dark:text-white group-hover:text-[#0F5F58] dark:group-hover:text-[#91D6CD] transition-colors block"
                    >
                      {d.name}
                    </Link>
                    <span className="text-xs text-[#6B7280] dark:text-slate-400 block mt-0.5">
                      {formatListingCount(d.stats.listing_count)} đang đăng
                    </span>
                  </div>

                  {/* Interquartile Range Strip */}
                  <div className="col-span-5 md:px-6">
                    <PriceRangeStrip
                      price={d.price}
                      size="md"
                      showLabels={true}
                    />
                  </div>

                  {/* Median Price */}
                  <div className="col-span-2 text-left md:text-right">
                    <div className="text-base font-bold text-[#111827] dark:text-white font-sans">
                      {metric === "month"
                        ? formatPrice(d.price.median, { perMonth: false, shortUnit: false })
                        : formatPricePerM2(d.price.median_per_m2)}
                    </div>
                    <span className="text-[11px] text-[#6B7280] dark:text-slate-400 block">
                      {metric === "month" ? "Trung vị tháng" : "Đơn giá m²"}
                    </span>
                  </div>

                  {/* 30-day Trend Badge & Link */}
                  <div className="col-span-2 flex items-center justify-between md:justify-end gap-3 text-xs">
                    <span className="text-[12px] text-ink-muted">
                      {formatListingCount(d.stats.priced_listing_count)} có giá
                    </span>
                    <Link
                      href={`/khu-vuc/${d.id}`}
                      className="text-[#0F5F58] dark:text-[#91D6CD] hover:underline font-medium hidden sm:inline"
                    >
                      Xem chi tiết →
                    </Link>
                  </div>
                </div>
              ))
            )}
          </div>
          {!searchDistrict.trim() && filtered.length > DEFAULT_ROWS && (
            <div className="border-t border-border-subtle px-6 py-4 text-center">
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                className="text-[13px] font-semibold text-brand hover:underline"
                aria-expanded={expanded}
              >
                {expanded ? "Thu gọn" : `Xem tất cả ${filtered.length} khu vực`}
              </button>
            </div>
          )}
          <p className="px-6 pb-5 text-[12px] text-ink-muted">
            Chỉ xếp hạng khu vực có từ {MIN_PRICED_LISTINGS} tin có giá hợp lệ trở lên để trung vị đủ ổn định.
          </p>
        </div>
      </div>
    </section>
  );
};
