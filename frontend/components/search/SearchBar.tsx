"use client";

import React, { useState, useEffect, useRef, useMemo } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { LocationPicker, SelectedLocation } from "./LocationPicker";
import { PriceFilter } from "./PriceFilter";
import {
  MapPin,
  Search,
  ChevronDown,
  SlidersHorizontal,
  X,
  ArrowRight,
  Sparkles,
  Banknote,
  Sliders,
} from "lucide-react";

interface SearchBarProps {
  initialValues?: {
    districtId?: string;
    districtName?: string;
    wardId?: string;
    wardName?: string;
    q?: string;
    priceMin?: number;
    priceMax?: number;
    areaMin?: number;
    areaMax?: number;
  };
  compact?: boolean;
  onSearch?: (params: Record<string, string>) => void;
  className?: string;
  showQuickChips?: boolean;
}

const PLACEHOLDERS = [
  "Đường, phường, hoặc tiện ích căn hộ…",
  "Gần ĐH Bách Khoa, có gác lửng…",
  "Studio ban công, giờ tự do…",
  "Căn hộ dịch vụ 1PN full nội thất…",
  "Gần khu công nghệ cao, thang máy…",
];

export const SearchBar: React.FC<SearchBarProps> = ({
  initialValues,
  compact = false,
  onSearch,
  className = "",
  showQuickChips = true,
}) => {
  const router = useRouter();

  const [selectedLoc, setSelectedLoc] = useState<SelectedLocation>({
    districtId: initialValues?.districtId,
    districtName: initialValues?.districtName,
    wardId: initialValues?.wardId,
    wardName: initialValues?.wardName,
  });
  const [q, setQ] = useState(initialValues?.q || "");
  const [priceMin, setPriceMin] = useState<number | undefined>(initialValues?.priceMin);
  const [priceMax, setPriceMax] = useState<number | undefined>(initialValues?.priceMax);
  const [areaMin, setAreaMin] = useState<number | undefined>(initialValues?.areaMin);
  const [areaMax, setAreaMax] = useState<number | undefined>(initialValues?.areaMax);

  const [pickerOpen, setPickerOpen] = useState(false);
  const [mobileSheetOpen, setMobileSheetOpen] = useState(false);
  const [placeholderIndex, setPlaceholderIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const interval = setInterval(() => {
      setPlaceholderIndex((prev) => (prev + 1) % PLACEHOLDERS.length);
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  const handleSearchSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();

    const params: Record<string, string> = {};
    if (selectedLoc.districtId) params.district_id = selectedLoc.districtId;
    if (selectedLoc.districtName) params.district_name = selectedLoc.districtName;
    if (selectedLoc.wardId) params.ward_id = selectedLoc.wardId;
    if (selectedLoc.wardName) params.ward_name = selectedLoc.wardName;
    if (q.trim()) params.q = q.trim();
    if (priceMin !== undefined) params.price_min = String(priceMin);
    if (priceMax !== undefined) params.price_max = String(priceMax);
    if (areaMin !== undefined) params.area_min = String(areaMin);
    if (areaMax !== undefined) params.area_max = String(areaMax);

    if (onSearch) {
      onSearch(params);
    } else {
      const searchStr = new URLSearchParams(params).toString();
      router.push(`/tim-phong${searchStr ? `?${searchStr}` : ""}`);
    }

    setMobileSheetOpen(false);
  };

  const locationDisplay = useMemo(() => {
    if (selectedLoc.wardName && selectedLoc.districtName) {
      return `${selectedLoc.wardName}, ${selectedLoc.districtName}`;
    }
    if (selectedLoc.districtName) {
      return selectedLoc.districtName;
    }
    return "Toàn TP.HCM";
  }, [selectedLoc]);

  const handleQuickChipPrice = (min?: number, max?: number) => {
    setPriceMin(min);
    setPriceMax(max);
    const params: Record<string, string> = {};
    if (selectedLoc.districtId) params.district_id = selectedLoc.districtId;
    if (min !== undefined) params.price_min = String(min);
    if (max !== undefined) params.price_max = String(max);
    if (onSearch) {
      onSearch(params);
    } else {
      const searchStr = new URLSearchParams(params).toString();
      router.push(`/tim-phong${searchStr ? `?${searchStr}` : ""}`);
    }
  };

  const handleQuickChipDistrict = (dId: string, dName: string) => {
    setSelectedLoc({ districtId: dId, districtName: dName });
    const params: Record<string, string> = { district_id: dId, district_name: dName };
    if (priceMin !== undefined) params.price_min = String(priceMin);
    if (priceMax !== undefined) params.price_max = String(priceMax);
    if (onSearch) {
      onSearch(params);
    } else {
      const searchStr = new URLSearchParams(params).toString();
      router.push(`/tim-phong${searchStr ? `?${searchStr}` : ""}`);
    }
  };

  return (
    <div className={`w-full ${className}`}>
      {/* DESKTOP SEARCH BAR (Pill Command Bar matching Design) */}
      <div className="hidden md:block w-full max-w-[1040px] mx-auto bg-white dark:bg-[#1A2234] rounded-full border border-[#E7E2DA] dark:border-slate-800 shadow-[0_14px_40px_rgba(17,24,39,0.07)] p-2 transition-all hover:shadow-[0_18px_50px_rgba(17,24,39,0.1)]">
        <form
          onSubmit={handleSearchSubmit}
          className="flex items-center divide-x divide-[#E7E2DA]/80 dark:divide-slate-800"
        >
          {/* Segment 1: Khu vực (22%) */}
          <div
            onClick={() => setPickerOpen(true)}
            className="w-[23%] px-5 py-2.5 text-left flex items-center gap-3 cursor-pointer group hover:bg-[#FAF8F5] dark:hover:bg-slate-800/60 rounded-l-full transition-colors"
          >
            <div className="w-8 h-8 rounded-full bg-[#0F5F58]/10 text-[#0F5F58] flex items-center justify-center shrink-0">
              <MapPin className="w-4 h-4 text-[#0F5F58]" />
            </div>
            <div className="min-w-0 flex-1">
              <span className="text-[11px] uppercase tracking-wider text-[#6B7280] dark:text-slate-400 block font-semibold leading-tight">
                Khu vực
              </span>
              <span className="text-sm font-semibold text-[#111827] dark:text-white truncate block group-hover:text-[#0F5F58] transition-colors">
                {locationDisplay} ▾
              </span>
            </div>
          </div>

          {/* Segment 2: Input search query (37%) */}
          <div className="w-[37%] px-5 py-2.5 text-left flex items-center gap-3">
            <Search className="w-4 h-4 text-[#6B7280] dark:text-slate-400 shrink-0" />
            <div className="w-full min-w-0">
              <span className="text-[11px] uppercase tracking-wider text-[#6B7280] dark:text-slate-400 block font-semibold leading-tight">
                Tìm kiếm
              </span>
              <input
                ref={inputRef}
                type="text"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={PLACEHOLDERS[placeholderIndex]}
                className="w-full bg-transparent text-sm text-[#111827] dark:text-white placeholder-[#9CA3AF] outline-none font-medium truncate"
              />
            </div>
            {q && (
              <button
                type="button"
                onClick={() => setQ("")}
                className="p-1 text-[#6B7280] hover:text-[#111827] rounded-full"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Segment 3: Khoảng giá (20%) */}
          <div className="w-[20%] px-4 py-2.5 text-left flex items-center justify-between group hover:bg-[#FAF8F5] dark:hover:bg-slate-800/60 transition-colors">
            <div className="min-w-0 flex-1">
              <span className="text-[11px] uppercase tracking-wider text-[#6B7280] dark:text-slate-400 block font-semibold leading-tight">
                Khoảng giá
              </span>
              <PriceFilter
                minPrice={priceMin}
                maxPrice={priceMax}
                onChange={(min, max) => {
                  setPriceMin(min);
                  setPriceMax(max);
                }}
                className="w-full"
              />
            </div>
          </div>

          {/* Segment 4: CTA Button (20%) */}
          <div className="w-[20%] pl-3 pr-1 py-1 flex justify-end">
            <button
              type="submit"
              className="w-full h-12 px-6 rounded-full bg-[#B8892E] hover:bg-[#a07424] active:scale-[0.98] text-white font-semibold text-sm shadow-sm flex items-center justify-center gap-2 transition-all cursor-pointer whitespace-nowrap"
            >
              <span>Tìm phòng</span>
              <ArrowRight className="w-4 h-4 stroke-[2.5]" />
            </button>
          </div>
        </form>
      </div>

      {/* QUICK FILTER CHIPS & VALUATION LINK (Home Hero) */}
      {showQuickChips && (
        <div className="mt-5 hidden md:flex flex-wrap justify-center items-center gap-2.5 text-xs text-[#4B5563] dark:text-slate-400">
          <span className="text-[11px] text-[#6B7280] uppercase tracking-wider font-semibold mr-1">
            Gợi ý nhanh:
          </span>
          <button
            type="button"
            onClick={() => handleQuickChipPrice(undefined, 3000000)}
            className="rounded-full bg-white dark:bg-[#1A2234] border border-[#E7E2DA] dark:border-slate-800 px-3.5 py-1.5 hover:border-[#0F5F58] hover:text-[#0F5F58] transition cursor-pointer font-medium"
          >
            Dưới 3 triệu
          </button>
          <button
            type="button"
            onClick={() => handleQuickChipPrice(3000000, 5000000)}
            className="rounded-full bg-white dark:bg-[#1A2234] border border-[#E7E2DA] dark:border-slate-800 px-3.5 py-1.5 hover:border-[#0F5F58] hover:text-[#0F5F58] transition cursor-pointer font-medium"
          >
            3–5 triệu
          </button>
          <button
            type="button"
            onClick={() => handleQuickChipDistrict("e2ed9f251d8cc334", "Quận 7")}
            className="rounded-full bg-white dark:bg-[#1A2234] border border-[#E7E2DA] dark:border-slate-800 px-3.5 py-1.5 hover:border-[#0F5F58] hover:text-[#0F5F58] transition cursor-pointer font-medium"
          >
            Quận 7
          </button>
          <button
            type="button"
            onClick={() => handleQuickChipDistrict("587c6c4ee67cfca2", "Bình Thạnh")}
            className="rounded-full bg-white dark:bg-[#1A2234] border border-[#E7E2DA] dark:border-slate-800 px-3.5 py-1.5 hover:border-[#0F5F58] hover:text-[#0F5F58] transition cursor-pointer font-medium"
          >
            Bình Thạnh
          </button>
          <button
            type="button"
            onClick={() => handleQuickChipDistrict("1ebf399f2a089938", "Gò Vấp")}
            className="rounded-full bg-white dark:bg-[#1A2234] border border-[#E7E2DA] dark:border-slate-800 px-3.5 py-1.5 hover:border-[#0F5F58] hover:text-[#0F5F58] transition cursor-pointer font-medium"
          >
            Gò Vấp
          </button>
          <Link
            href="/dinh-gia"
            className="inline-flex items-center gap-1.5 font-medium text-[#0F5F58] hover:text-[#0b4742] dark:text-[#91D6CD] ml-3 transition group"
          >
            <span className="underline underline-offset-4 decoration-[#0F5F58]/40 group-hover:decoration-[#0F5F58]">
              Định giá phòng của bạn
            </span>
            <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" />
          </Link>
        </div>
      )}

      {/* MOBILE TRIGGER PILL */}
      <div className="flex md:hidden w-full px-2">
        <button
          type="button"
          onClick={() => setMobileSheetOpen(true)}
          className="w-full h-14 bg-white dark:bg-[#1A2234] rounded-full border border-[#E7E2DA] dark:border-slate-800 shadow-[0_8px_24px_rgba(17,24,39,0.06)] px-4 flex items-center justify-between text-left"
        >
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="w-8 h-8 rounded-full bg-[#0F5F58]/10 text-[#0F5F58] flex items-center justify-center shrink-0">
              <Search className="w-4 h-4 text-[#0F5F58]" />
            </div>
            <div className="truncate">
              <span className="text-sm font-semibold text-[#111827] dark:text-white block truncate">
                {q || "Tìm phòng ở TP. Hồ Chí Minh…"}
              </span>
              <span className="text-xs text-[#6B7280] dark:text-slate-400 block truncate">
                {locationDisplay} · {priceMin || priceMax ? "Đã lọc giá" : "Mọi mức giá"}
              </span>
            </div>
          </div>
          <div className="p-2 rounded-full bg-[#FAF8F5] dark:bg-slate-800 text-[#0F5F58] shrink-0">
            <SlidersHorizontal className="w-4 h-4" />
          </div>
        </button>
      </div>

      {/* MOBILE FULL-SCREEN BOTTOM SHEET (Matching Design) */}
      {mobileSheetOpen && (
        <div className="fixed inset-0 z-50 flex flex-col justify-end bg-black/50 backdrop-blur-sm md:hidden animate-fade-in">
          <div
            className="w-full bg-white dark:bg-[#1A2234] rounded-t-[28px] shadow-2xl p-5 flex flex-col max-h-[92vh] overflow-hidden animate-[slideUp_0.35s_cubic-bezier(0.16,1,0.3,1)]"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Drag Handle */}
            <div className="w-12 h-1 rounded-full bg-[#E7E2DA] dark:bg-slate-700 mx-auto mb-3" />

            {/* Sheet Header */}
            <div className="flex items-center justify-between pb-3 border-b border-[#E7E2DA] dark:border-slate-800 mb-4">
              <button
                type="button"
                onClick={() => setMobileSheetOpen(false)}
                className="w-9 h-9 rounded-full bg-[#FAF8F5] dark:bg-slate-800 flex items-center justify-center text-[#111827] dark:text-white"
              >
                <X className="w-5 h-5" />
              </button>
              <div className="text-center">
                <span className="text-[10px] uppercase tracking-widest text-[#0F5F58] font-bold block">
                  RoomBeacon Select
                </span>
                <h3 className="font-bold text-base text-[#111827] dark:text-white font-display">
                  Bộ lọc tìm phòng
                </h3>
              </div>
              <button
                type="button"
                onClick={() => {
                  setSelectedLoc({});
                  setQ("");
                  setPriceMin(undefined);
                  setPriceMax(undefined);
                  setAreaMin(undefined);
                  setAreaMax(undefined);
                }}
                className="text-xs font-semibold text-[#B8892E] hover:underline"
              >
                Thiết lập lại
              </button>
            </div>

            {/* Scrollable Filter Body */}
            <div className="flex-1 overflow-y-auto space-y-5 pb-6">
              {/* Section 1: Khu vực */}
              <div>
                <label className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider block mb-2">
                  Khu vực tìm kiếm
                </label>
                <button
                  type="button"
                  onClick={() => setPickerOpen(true)}
                  className="w-full p-3.5 bg-[#FAF8F5] dark:bg-slate-900 rounded-xl border border-[#E7E2DA] dark:border-slate-800 flex items-center justify-between text-left"
                >
                  <div className="flex items-center gap-2.5 truncate">
                    <MapPin className="w-4 h-4 text-[#0F5F58] shrink-0" />
                    <span className="text-sm font-semibold text-[#111827] dark:text-white truncate">
                      {locationDisplay}
                    </span>
                  </div>
                  <ChevronDown className="w-4 h-4 text-[#6B7280] shrink-0" />
                </button>

                {/* Quick neighborhood chips */}
                <div className="flex flex-wrap gap-1.5 pt-2">
                  {["Quận 7", "Bình Thạnh", "Quận 1", "Gò Vấp", "Tân Bình"].map((name) => (
                    <button
                      key={name}
                      type="button"
                      onClick={() => {
                        setSelectedLoc((prev) => ({ ...prev, districtName: name }));
                      }}
                      className="px-3 py-1 rounded-full text-xs font-medium bg-[#FAF8F5] dark:bg-slate-800 border border-[#E7E2DA] dark:border-slate-700 text-[#111827] dark:text-white hover:border-[#0F5F58]"
                    >
                      {name}
                    </button>
                  ))}
                </div>
              </div>

              {/* Section 2: Từ khoá */}
              <div>
                <label className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider block mb-1.5">
                  Từ khoá hoặc tên đường
                </label>
                <div className="relative flex items-center">
                  <Search className="w-4 h-4 text-[#6B7280] absolute left-3.5" />
                  <input
                    type="text"
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    placeholder="Tên đường, toà nhà, tiện ích…"
                    className="w-full pl-10 pr-4 py-2.5 text-sm rounded-xl bg-[#FAF8F5] dark:bg-slate-900 border border-[#E7E2DA] dark:border-slate-800 text-[#111827] dark:text-white outline-none"
                  />
                </div>
              </div>

              {/* Section 3: Mức giá */}
              <div>
                <label className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider block mb-2">
                  Khoảng giá thuê
                </label>
                <PriceFilter
                  minPrice={priceMin}
                  maxPrice={priceMax}
                  onChange={(min, max) => {
                    setPriceMin(min);
                    setPriceMax(max);
                  }}
                  className="w-full"
                />
              </div>
            </div>

            {/* Bottom Submit Button */}
            <div className="pt-3 border-t border-[#E7E2DA] dark:border-slate-800">
              <button
                type="button"
                onClick={() => handleSearchSubmit()}
                className="w-full py-3.5 bg-[#B8892E] text-white font-bold rounded-full shadow-lg flex items-center justify-center gap-2 cursor-pointer active:scale-[0.99] transition-all"
              >
                <Search className="w-4 h-4 stroke-[2.5]" />
                <span>Xem kết quả tìm kiếm</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* LOCATION PICKER MODAL */}
      <LocationPicker
        isOpen={pickerOpen}
        onClose={() => setPickerOpen(false)}
        selected={selectedLoc}
        onSelect={(loc) => setSelectedLoc(loc)}
      />
    </div>
  );
};
