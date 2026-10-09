"use client";

import React, { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useEstimate, useDistricts } from "@/lib/api/hooks";
import { LocationPicker, SelectedLocation } from "@/components/search/LocationPicker";
import { EstimateResult } from "./EstimateResult";
import { ModelCardDrawer } from "./ModelCardDrawer";
import type { PriceEstimate } from "@/lib/types/api";
import {
  MapPin,
  Sliders,
  Sparkles,
  AlertCircle,
  HelpCircle,
  Check,
  ChevronDown,
  Gauge,
} from "lucide-react";

export const EstimateForm: React.FC = () => {
  const searchParams = useSearchParams();
  const initialDistrictId = searchParams?.get("district_id") || "e2ed9f251d8cc334"; // Default Q7
  const initialWardId = searchParams?.get("ward_id") || "";
  const initialArea = searchParams?.get("area") ? Number(searchParams?.get("area")) : 25;

  const [selectedLoc, setSelectedLoc] = useState<SelectedLocation>({
    districtId: initialDistrictId,
    districtName: "Quận 7",
    wardId: initialWardId || undefined,
  });
  const [areaM2, setAreaM2] = useState<number>(initialArea);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [modelDrawerOpen, setModelDrawerOpen] = useState(false);
  const [estimateResult, setEstimateResult] = useState<PriceEstimate | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  // Fetch districts to display name
  const { data: districtsRes } = useDistricts({ per_page: 55 });

  useEffect(() => {
    if (initialDistrictId && districtsRes?.data) {
      const match = districtsRes.data.find((d) => d.id === initialDistrictId);
      if (match) {
        setSelectedLoc((prev) => ({
          ...prev,
          districtId: match.id,
          districtName: match.name,
        }));
      }
    }
  }, [initialDistrictId, districtsRes]);

  const { mutate: runEstimate, isPending } = useEstimate();

  const handleRun = (dId?: string, wId?: string, area?: number) => {
    const targetDistrictId = dId || selectedLoc.districtId;
    if (!targetDistrictId) {
      setFormError("Vui lòng chọn quận/huyện để mô hình xác định vị trí.");
      return;
    }

    const targetArea = area || areaM2;
    if (!targetArea || targetArea < 5 || targetArea > 500) {
      setFormError("Diện tích hợp lệ từ 5 đến 500 m².");
      return;
    }

    setFormError(null);
    runEstimate(
      {
        area_m2: Number(targetArea),
        district_id: targetDistrictId,
        ward_id: wId || selectedLoc.wardId,
      },
      {
        onSuccess: (res) => {
          if (res.data) {
            setEstimateResult(res.data);
          } else {
            setFormError(res.message || "Không thể ước tính giá cho thông tin này.");
          }
        },
        onError: (err: any) => {
          setFormError(err.message || "Lỗi kết nối khi gửi yêu cầu định giá.");
        },
      }
    );
  };

  // Run automatically on mount if district present
  useEffect(() => {
    if (selectedLoc.districtId && !estimateResult) {
      handleRun(selectedLoc.districtId, selectedLoc.wardId, areaM2);
    }
  }, [selectedLoc.districtId]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleRun();
  };

  const locationDisplayText = selectedLoc.districtName
    ? selectedLoc.wardName
      ? `${selectedLoc.wardName}, ${selectedLoc.districtName}`
      : selectedLoc.districtName
    : "Chọn Phường, Quận...";

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
      {/* LEFT COLUMN: Real Estate Parameter Card (col-span-12 lg:col-span-5) */}
      <div className="lg:col-span-5 bg-white dark:bg-[#1A2234] rounded-2xl p-6 sm:p-7 border border-[#E7E2DA] dark:border-slate-800 shadow-sm space-y-6">
        <div>
          <span className="text-[11px] uppercase tracking-wider text-[#0F5F58] dark:text-[#91D6CD] font-semibold block mb-1">
            Thông số định giá
          </span>
          <h2 className="font-display text-xl font-medium text-[#111827] dark:text-white">
            Nhập thông tin căn phòng
          </h2>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Field 1: Location Trigger */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-[#111827] dark:text-white block">
              Vị trí căn phòng
            </label>
            <div
              onClick={() => setPickerOpen(true)}
              className="w-full p-3.5 bg-[#FAF8F5] dark:bg-slate-900 rounded-xl border border-[#E7E2DA] dark:border-slate-800 flex items-center justify-between cursor-pointer hover:border-[#0F5F58] transition-colors group"
            >
              <div className="flex items-center gap-3 min-w-0">
                <MapPin className="w-5 h-5 text-[#0F5F58] shrink-0" />
                <div className="truncate text-left">
                  <div className="text-sm font-semibold text-[#111827] dark:text-white truncate group-hover:text-[#0F5F58] transition-colors">
                    {locationDisplayText}
                  </div>
                  <div className="text-[11px] text-[#6B7280] dark:text-slate-400">
                    Quận bắt buộc, phường tùy chọn
                  </div>
                </div>
              </div>
              <ChevronDown className="w-4 h-4 text-[#9CA3AF] shrink-0" />
            </div>
          </div>

          {/* Field 3: Usable Area Slider */}
          <div className="space-y-3 bg-[#FAF8F5] dark:bg-slate-900/60 rounded-xl p-4 border border-[#E7E2DA]/80 dark:border-slate-800">
            <div className="flex items-center justify-between">
              <div>
                <label className="text-xs font-semibold text-[#111827] dark:text-white block">
                  Diện tích sử dụng
                </label>
                <div className="text-[11px] text-[#6B7280]">Theo tin đăng hoặc hợp đồng</div>
              </div>
              <div className="flex items-center bg-white dark:bg-slate-800 border border-[#E7E2DA] dark:border-slate-700 rounded-lg px-2.5 py-1 shadow-2xs">
                <input
                  type="number"
                  min={5}
                  max={120}
                  value={areaM2}
                  onChange={(e) => setAreaM2(Number(e.target.value))}
                  className="w-12 text-right font-display text-lg font-bold text-[#0F5F58] dark:text-[#91D6CD] outline-none bg-transparent"
                />
                <span className="text-xs font-semibold text-[#6B7280] ml-1">m²</span>
              </div>
            </div>

            <div className="pt-1">
              <input
                type="range"
                min={10}
                max={80}
                step={1}
                value={Math.min(Math.max(areaM2, 10), 80)}
                onChange={(e) => setAreaM2(Number(e.target.value))}
                className="w-full accent-[#0F5F58] h-2 bg-[#E7E2DA] dark:bg-slate-800 rounded-lg cursor-pointer"
              />
              <div className="flex justify-between text-[10px] text-[#6B7280] mt-1 pt-1 border-t border-[#E7E2DA]/50">
                <span>10m²</span>
                <span>25m²</span>
                <span className="text-[#0F5F58] font-bold">50m²</span>
                <span>80m²</span>
              </div>
            </div>
          </div>

          {/* Form Error */}
          {formError && (
            <div className="p-3 bg-[#FEF2F2] border border-red-200 rounded-xl text-xs text-[#B91C1C] flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{formError}</span>
            </div>
          )}

          {/* Primary Submit Button */}
          <button
            type="submit"
            disabled={isPending}
            className="w-full py-4 px-6 rounded-full bg-[#B8892E] hover:bg-[#a07424] text-white font-semibold text-sm shadow-md transition-all flex items-center justify-center gap-2 cursor-pointer active:scale-[0.99] disabled:opacity-50"
          >
            <span>{isPending ? "Đang ước tính…" : "Định giá ngay"}</span>
            <Gauge className="w-4 h-4 stroke-[2.5]" />
          </button>
        </form>
      </div>

      {/* RIGHT COLUMN: Large Result Card & Market Intelligence (col-span-12 lg:col-span-7) */}
      <div className="lg:col-span-7">
        {estimateResult ? (
          <EstimateResult
            estimate={estimateResult}
            districtId={selectedLoc.districtId || ""}
            wardId={selectedLoc.wardId}
            onOpenModelCard={() => setModelDrawerOpen(true)}
          />
        ) : (
          <div className="bg-white dark:bg-[#1A2234] rounded-2xl p-12 border border-[#E7E2DA] dark:border-slate-800 text-center shadow-xs flex flex-col items-center justify-center min-h-[380px]">
            <Sparkles className="w-12 h-12 text-[#0F5F58]/30 mb-3" />
            <h3 className="font-display text-lg font-medium text-[#111827] dark:text-white mb-1">
              Sẵn sàng định giá
            </h3>
            <p className="text-xs text-[#6B7280] max-w-sm">
              Chọn khu vực và diện tích ở bảng bên trái, sau đó bấm &ldquo;Định giá ngay&rdquo; để nhận kết quả phân tích tức thì.
            </p>
          </div>
        )}
      </div>

      {/* Location Picker Modal */}
      <LocationPicker
        isOpen={pickerOpen}
        onClose={() => setPickerOpen(false)}
        selected={selectedLoc}
        onSelect={(loc) => {
          setSelectedLoc(loc);
          if (loc.districtId) {
            handleRun(loc.districtId, loc.wardId, areaM2);
          }
        }}
      />

      {/* Model Technical Card Drawer */}
      <ModelCardDrawer
        isOpen={modelDrawerOpen}
        onClose={() => setModelDrawerOpen(false)}
      />
    </div>
  );
};
