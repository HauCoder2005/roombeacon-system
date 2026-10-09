"use client";

import React, { useState, useEffect, useRef, useMemo } from "react";
import { useDistricts, useDistrictWards, useResolveWard } from "@/lib/api/hooks";
import {
  getRecentLocations,
  saveRecentLocation,
  clearRecentLocations,
  StoredLocation,
} from "@/lib/recentLocations";
import { formatListingCount, formatPrice } from "@/lib/format";
import type { DistrictCard, WardCard } from "@/lib/types/api";
import {
  MapPin,
  Search,
  ChevronRight,
  ChevronLeft,
  X,
  Clock,
  Check,
  Building2,
  Compass,
  AlertCircle,
  Radio,
} from "lucide-react";

export interface SelectedLocation {
  districtId?: string;
  districtName?: string;
  wardId?: string;
  wardName?: string;
}

interface LocationPickerProps {
  isOpen: boolean;
  onClose: () => void;
  selected: SelectedLocation;
  onSelect: (loc: SelectedLocation) => void;
}

export const LocationPicker: React.FC<LocationPickerProps> = ({
  isOpen,
  onClose,
  selected,
  onSelect,
}) => {
  const [step, setStep] = useState<1 | 2>(1);
  const [activeDistrict, setActiveDistrict] = useState<DistrictCard | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [recentList, setRecentList] = useState<StoredLocation[]>([]);

  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setRecentList(getRecentLocations());
    }
  }, [isOpen]);

  // Debounce search query 300ms
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(searchQuery.trim());
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen, step]);

  useEffect(() => {
    if (!isOpen) {
      setStep(1);
      setActiveDistrict(null);
      setSearchQuery("");
      setDebouncedQuery("");
    }
  }, [isOpen]);

  const { data: districtsData, isLoading: loadingDistricts } = useDistricts({
    q: step === 1 ? debouncedQuery : "",
    per_page: 55,
    sort: "-listing_count",
  });

  const { data: wardsData, isLoading: loadingWards } = useDistrictWards(
    activeDistrict?.id,
    { q: step === 2 ? debouncedQuery : "", per_page: 50, sort: "-listing_count" }
  );

  const isWardQuery = step === 1 && debouncedQuery.length >= 2;

  const wardQueryToResolve = useMemo(() => {
    if (!debouncedQuery) return "";
    const lower = debouncedQuery.toLowerCase();
    if (lower.startsWith("phường") || lower.startsWith("p.") || lower.startsWith("p ")) {
      return debouncedQuery;
    }
    return `Phường ${debouncedQuery}`;
  }, [debouncedQuery]);

  const { data: resolveData, isLoading: resolvingWard } = useResolveWard(
    wardQueryToResolve,
    undefined,
    isWardQuery
  );

  const districts = districtsData?.data || [];
  const wards = wardsData?.data || [];

  const handleSelectAllHcm = () => {
    saveRecentLocation({ label: "Toàn TP.HCM" });
    onSelect({});
    onClose();
  };

  const handleSelectDistrictOnly = (district: DistrictCard) => {
    saveRecentLocation({
      districtId: district.id,
      districtName: district.name,
      label: district.name,
    });
    onSelect({ districtId: district.id, districtName: district.name });
    onClose();
  };

  const handleSelectWard = (district: { id: string; name: string }, ward: WardCard) => {
    saveRecentLocation({
      districtId: district.id,
      districtName: district.name,
      wardId: ward.id,
      wardName: ward.name,
      label: `${ward.name}, ${district.name}`,
    });
    onSelect({
      districtId: district.id,
      districtName: district.name,
      wardId: ward.id,
      wardName: ward.name,
    });
    onClose();
  };

  const handleSelectRecent = (item: StoredLocation) => {
    onSelect({
      districtId: item.districtId,
      districtName: item.districtName,
      wardId: item.wardId,
      wardName: item.wardName,
    });
    onClose();
  };

  const handleClearHistory = () => {
    clearRecentLocations();
    setRecentList([]);
  };

  const handleDistrictClick = (district: DistrictCard) => {
    setActiveDistrict(district);
    setSearchQuery("");
    setDebouncedQuery("");
    setStep(2);
  };

  const handleBackToStep1 = () => {
    setStep(1);
    setActiveDistrict(null);
    setSearchQuery("");
    setDebouncedQuery("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      onClose();
    } else if (e.key === "Backspace" && searchQuery === "" && step === 2) {
      handleBackToStep1();
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-black/40 backdrop-blur-sm animate-fade-in"
      role="dialog"
      aria-modal="true"
      aria-labelledby="location-picker-title"
      onClick={onClose}
    >
      <div
        className="w-full sm:w-[480px] bg-white dark:bg-[#1A2234] rounded-t-[28px] sm:rounded-2xl shadow-[0_20px_45px_rgba(17,24,39,0.14)] border border-[#E7E2DA] dark:border-slate-800 overflow-hidden flex flex-col max-h-[88vh] sm:max-h-[640px] animate-[slideUp_0.25s_ease-out]"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        {/* Modal Header */}
        <div className="p-4 border-b border-[#E7E2DA] dark:border-slate-800 flex items-center justify-between bg-[#FAF8F5]/80 dark:bg-slate-900/60">
          <div className="flex items-center gap-2">
            {step === 2 && (
              <button
                type="button"
                onClick={handleBackToStep1}
                className="w-8 h-8 -ml-1 text-[#6B7280] hover:text-[#111827] dark:hover:text-white rounded-full hover:bg-black/5 dark:hover:bg-white/10 flex items-center justify-center transition-colors"
                aria-label="Quay lại chọn quận"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
            )}
            <div>
              <span className="text-[10px] font-semibold text-[#0F5F58] dark:text-[#91D6CD] uppercase tracking-wider block">
                {step === 1 ? "Bước 1 · Chọn khu vực" : "Bước 2 · Chọn phường"}
              </span>
              <h2 id="location-picker-title" className="font-semibold text-base text-[#111827] dark:text-white">
                {step === 1 ? "Khu vực tìm kiếm" : activeDistrict?.name}
              </h2>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 text-[#6B7280] hover:text-[#111827] dark:hover:text-white rounded-full hover:bg-black/5 dark:hover:bg-white/10 flex items-center justify-center transition-colors"
            aria-label="Đóng"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Search Input Bar */}
        <div className="p-3.5 border-b border-[#E7E2DA] dark:border-slate-800 bg-white dark:bg-[#1A2234]">
          <div className="relative flex items-center">
            <Search className="w-4 h-4 text-[#6B7280] absolute left-3.5 pointer-events-none" />
            <input
              ref={inputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={
                step === 1
                  ? "Tìm quận, huyện hoặc thành phố…"
                  : `Tìm phường thuộc ${activeDistrict?.name || ""}…`
              }
              className="w-full pl-10 pr-14 py-2.5 text-sm rounded-xl bg-[#FAF8F5] dark:bg-slate-900 border border-[#E7E2DA] dark:border-slate-800 text-[#111827] dark:text-white placeholder:text-[#9CA3AF] focus:bg-white dark:focus:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-[#0F5F58]/25 transition-all"
            />
            {searchQuery ? (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="absolute right-3 p-1 text-[#6B7280] hover:text-[#111827] rounded-full"
                aria-label="Xoá tìm kiếm"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            ) : (
              <span className="absolute right-3 px-1.5 py-0.5 text-[10px] font-semibold text-[#6B7280] bg-white dark:bg-slate-800 border border-[#E7E2DA] dark:border-slate-700 rounded select-none pointer-events-none">
                ESC
              </span>
            )}
          </div>
        </div>

        {/* Modal Scrollable Body */}
        <div className="overflow-y-auto flex-1 p-3 space-y-2 overscroll-contain">
          {/* STEP 3 DISAMBIGUATION NOTICE (Ambiguous Ward Resolution) */}
          {isWardQuery && (
            <div className="pb-2 space-y-2">
              <div className="px-1 py-1 flex items-center justify-between">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-[#0F5F58] dark:text-[#91D6CD]">
                  Phân định địa giới
                </span>
                {resolvingWard && (
                  <span className="text-xs text-[#6B7280]">Đang tra cứu…</span>
                )}
              </div>

              {resolveData?.type === "single" && (
                <button
                  type="button"
                  onClick={() =>
                    handleSelectWard(resolveData.ward.district, resolveData.ward)
                  }
                  className="w-full p-3 text-left rounded-xl bg-[#0F5F58]/10 hover:bg-[#0F5F58]/15 border border-[#0F5F58]/20 flex items-center justify-between transition-colors group"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-[#0F5F58] text-white flex items-center justify-center shrink-0">
                      <MapPin className="w-4 h-4" />
                    </div>
                    <div>
                      <span className="font-semibold text-sm text-[#111827] dark:text-white">
                        {resolveData.ward.name}
                      </span>
                      <span className="text-xs text-[#0F5F58] dark:text-[#91D6CD] block font-medium">
                        Thuộc {resolveData.ward.district.name} · {formatListingCount(resolveData.ward.stats.listing_count)}
                      </span>
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-[#0F5F58]" />
                </button>
              )}

              {resolveData?.type === "choices" && (
                <div className="space-y-2">
                  {/* Step 3 Banner */}
                  <div className="p-3 rounded-xl bg-[#FEF3C7] dark:bg-amber-950/40 border border-[#FDE68A] dark:border-amber-800 text-[#92400E] dark:text-amber-200 flex items-start gap-2.5">
                    <AlertCircle className="w-4 h-4 text-[#B45309] dark:text-amber-400 shrink-0 mt-0.5" />
                    <div className="text-xs leading-relaxed">
                      <strong>Trùng tên phường:</strong> &ldquo;{debouncedQuery}&rdquo; có ở nhiều quận khác nhau. Vui lòng chọn địa giới chính xác:
                    </div>
                  </div>

                  {resolveData.choices.map((choice) => (
                    <button
                      key={choice.id}
                      type="button"
                      onClick={() => handleSelectWard(choice.district, choice)}
                      className="w-full p-3 text-left rounded-xl bg-white dark:bg-slate-900 hover:bg-[#FAF8F5] dark:hover:bg-slate-800 border border-[#E7E2DA] dark:border-slate-800 flex items-center justify-between transition-all group"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-[#FAF8F5] dark:bg-slate-800 border border-[#E7E2DA] dark:border-slate-700 text-[#0F5F58] flex items-center justify-center shrink-0 group-hover:bg-[#0F5F58] group-hover:text-white transition-colors">
                          <MapPin className="w-4 h-4" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-sm text-[#111827] dark:text-white">
                              {choice.name}
                            </span>
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-[#0F5F58]/10 text-[#0F5F58]">
                              {choice.district.name}
                            </span>
                          </div>
                          <span className="text-xs text-[#6B7280] dark:text-slate-400 block mt-0.5">
                            {formatListingCount(choice.stats.listing_count)} · Trung vị {formatPrice(choice.price.median, { shortUnit: true })}
                          </span>
                        </div>
                      </div>
                      <ChevronRight className="w-4 h-4 text-[#6B7280] group-hover:text-[#0F5F58] transition-colors" />
                    </button>
                  ))}
                </div>
              )}

              {resolveData?.type === "not_found" && (
                <div className="p-3 text-xs text-[#6B7280] italic text-center">
                  Không tìm thấy phường trùng khớp. Vui lòng chọn theo danh sách quận bên dưới.
                </div>
              )}
            </div>
          )}

          {/* STEP 1: ALL HCM & DISTRICTS */}
          {step === 1 && !isWardQuery && (
            <>
              {/* Recent quick chips (Gần đây) */}
              {!debouncedQuery && recentList.length > 0 && (
                <div className="px-1 pt-1 pb-2">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[11px] font-semibold text-[#6B7280] dark:text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                      <Clock className="w-3.5 h-3.5 text-[#0F5F58]" />
                      Gần đây
                    </span>
                    <button
                      type="button"
                      onClick={handleClearHistory}
                      className="text-[11px] font-medium text-[#6B7280] hover:text-[#111827] dark:hover:text-white transition-colors"
                    >
                      Xoá lịch sử
                    </button>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    {recentList.map((item, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => handleSelectRecent(item)}
                        className="px-3 py-1.5 rounded-full bg-[#FAF8F5] dark:bg-slate-900 hover:bg-[#E7E2DA] dark:hover:bg-slate-800 border border-[#E7E2DA] dark:border-slate-800 text-[#111827] dark:text-white text-xs font-medium flex items-center gap-1.5 transition-all group"
                      >
                        <Clock className="w-3 h-3 text-[#0F5F58] group-hover:scale-110 transition-transform" />
                        <span className="truncate max-w-[140px]">{item.label}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {!debouncedQuery && <div className="h-px bg-[#E7E2DA] dark:bg-slate-800 my-1" />}

              {/* Item 1: Toàn TP.HCM */}
              {!debouncedQuery && (
                <div
                  onClick={handleSelectAllHcm}
                  className={`flex items-center justify-between p-3 rounded-xl cursor-pointer transition-colors ${
                    !selected.districtId
                      ? "bg-[#0F5F58]/10 text-[#0F5F58] font-semibold"
                      : "hover:bg-[#FAF8F5] dark:hover:bg-slate-800 text-[#111827] dark:text-white"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-[#0F5F58] text-white flex items-center justify-center shrink-0">
                      <Compass className="w-5 h-5" />
                    </div>
                    <div className="flex flex-col text-left">
                      <div className="flex items-center gap-1.5">
                        <span className="text-sm font-semibold text-[#111827] dark:text-white">
                          Toàn TP.HCM
                        </span>
                        <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-[#0F5F58] text-white uppercase">
                          Tất cả
                        </span>
                      </div>
                      <span className="text-xs text-[#6B7280] dark:text-slate-400">
                        55 quận / huyện và khu vực · 76.531 tin đăng
                      </span>
                    </div>
                  </div>
                  {!selected.districtId && <Check className="w-5 h-5 text-[#0F5F58]" />}
                </div>
              )}

              {/* Districts Directory List */}
              <div className="space-y-1 pt-1">
                {!debouncedQuery && (
                  <div className="px-2 py-1 text-[11px] font-semibold text-[#6B7280] dark:text-slate-400 uppercase tracking-wider">
                    55 Quận / Huyện &amp; Khu vực
                  </div>
                )}
                {loadingDistricts ? (
                  <div className="p-6 text-center text-xs text-[#6B7280]">
                    Đang tải danh sách khu vực…
                  </div>
                ) : districts.length === 0 ? (
                  <div className="p-6 text-center text-xs text-[#6B7280]">
                    Không tìm thấy khu vực phù hợp.
                  </div>
                ) : (
                  districts.map((district) => {
                    const isSelected = selected.districtId === district.id && !selected.wardId;
                    return (
                      <div
                        key={district.id}
                        onClick={() => handleDistrictClick(district)}
                        className={`flex items-center justify-between p-2.5 rounded-xl cursor-pointer transition-colors group ${
                          isSelected
                            ? "bg-[#0F5F58]/10 text-[#0F5F58]"
                            : "hover:bg-[#FAF8F5] dark:hover:bg-slate-800"
                        }`}
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="w-9 h-9 rounded-lg bg-[#FAF8F5] dark:bg-slate-800 text-[#6B7280] flex items-center justify-center shrink-0 group-hover:bg-[#0F5F58] group-hover:text-white transition-colors">
                            <Building2 className="w-4 h-4" />
                          </div>
                          <div className="flex flex-col text-left min-w-0">
                            <span className="text-sm font-semibold text-[#111827] dark:text-white group-hover:text-[#0F5F58] transition-colors truncate">
                              {district.name}
                            </span>
                            <span className="text-xs text-[#6B7280] dark:text-slate-400 truncate">
                              {formatListingCount(district.stats.listing_count)} · Trung vị{" "}
                              <strong className="text-[#111827] dark:text-white font-semibold">
                                {formatPrice(district.price.median, { shortUnit: true })}
                              </strong>
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          {district.stats.listing_count > 5000 && (
                            <span className="text-[11px] font-medium text-[#047857] bg-[#ECFDF5] px-2 py-0.5 rounded-full hidden sm:inline">
                              Nhiều tin
                            </span>
                          )}
                          <ChevronRight className="w-4 h-4 text-[#9CA3AF] group-hover:text-[#0F5F58] group-hover:translate-x-0.5 transition-transform" />
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </>
          )}

          {/* STEP 2: WARDS SELECTION */}
          {step === 2 && activeDistrict && (
            <div className="space-y-1">
              {/* Default Choice: Toàn Quận */}
              <div
                onClick={() => handleSelectDistrictOnly(activeDistrict)}
                className={`flex items-center justify-between p-3 rounded-xl cursor-pointer transition-colors ${
                  selected.districtId === activeDistrict.id && !selected.wardId
                    ? "bg-[#0F5F58]/10 text-[#0F5F58]"
                    : "hover:bg-[#FAF8F5] dark:hover:bg-slate-800 bg-[#FAF8F5]/60"
                }`}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-7 h-7 rounded-full bg-[#0F5F58] text-white flex items-center justify-center shrink-0 shadow-sm">
                    <Check className="w-4 h-4" />
                  </div>
                  <div className="flex flex-col min-w-0">
                    <span className="text-sm font-bold text-[#0F5F58] dark:text-[#91D6CD] truncate">
                      Toàn {activeDistrict.name}
                    </span>
                    <span className="text-xs text-[#6B7280] dark:text-slate-400 truncate">
                      Tất cả phường · Giá trung vị {formatPrice(activeDistrict.price.median, { shortUnit: false })}
                    </span>
                  </div>
                </div>
                <span className="text-xs font-semibold text-[#0F5F58] shrink-0">
                  {formatListingCount(activeDistrict.stats.listing_count)}
                </span>
              </div>

              <div className="h-px bg-[#E7E2DA] dark:bg-slate-800 my-2" />

              <div className="px-2 py-1 text-[11px] font-semibold text-[#6B7280] dark:text-slate-400 uppercase tracking-wider">
                Phường thuộc {activeDistrict.name}
              </div>

              {loadingWards ? (
                <div className="p-6 text-center text-xs text-[#6B7280]">Đang tải danh sách phường…</div>
              ) : wards.length === 0 ? (
                <div className="p-6 text-center text-xs text-[#6B7280]">Không tìm thấy phường phù hợp.</div>
              ) : (
                wards.map((ward, idx) => {
                  const isSelected = selected.wardId === ward.id;
                  return (
                    <div
                      key={ward.id}
                      onClick={() => handleSelectWard(activeDistrict, ward)}
                      className={`flex items-center justify-between p-3 rounded-xl cursor-pointer transition-colors group ${
                        isSelected
                          ? "bg-[#0F5F58]/10 text-[#0F5F58]"
                          : "hover:bg-[#FAF8F5] dark:hover:bg-slate-800"
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div
                          className={`w-5 h-5 rounded-full border flex items-center justify-center shrink-0 transition-colors ${
                            isSelected
                              ? "border-[#0F5F58] bg-[#0F5F58] text-white"
                              : "border-[#D1D5DB] group-hover:border-[#0F5F58]"
                          }`}
                        >
                          {isSelected && <Check className="w-3 h-3 stroke-[3]" />}
                        </div>
                        <div className="flex flex-col min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-[#111827] dark:text-white group-hover:text-[#0F5F58] transition-colors truncate">
                              {ward.name}
                            </span>
                            {idx === 0 && ward.stats.listing_count > 0 && (
                              <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full bg-[#047857]/10 text-[#047857] font-semibold shrink-0">
                                Nhiều tin nhất
                              </span>
                            )}
                          </div>
                          <span className="text-xs text-[#6B7280] dark:text-slate-400 truncate">
                            Giá trung vị: {formatPrice(ward.price.median, { shortUnit: false })}
                          </span>
                        </div>
                      </div>
                      <span className="text-xs text-[#6B7280] dark:text-slate-400 font-medium shrink-0">
                        {formatListingCount(ward.stats.listing_count)}
                      </span>
                    </div>
                  );
                })
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
