import React from "react";
import type { Metadata } from "next";
import { getServerDistricts } from "@/lib/api/server";
import { DistrictCard } from "@/components/cards/DistrictCard";
import { MapPin } from "lucide-react";

export const metadata: Metadata = {
  title: "Danh sách khu vực & quận huyện TP.HCM — RoomBeacon",
  description:
    "Tổng quan dữ liệu giá thuê phòng trọ, căn hộ tại các quận huyện và TP Thủ Đức, TP.HCM.",
};

export default async function DistrictsPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; sort?: string }>;
}) {
  const { q = "", sort = "-listing_count" } = await searchParams;

  let districtsData = null;
  try {
    districtsData = await getServerDistricts({ q, sort, per_page: 55 });
  } catch {
    // fallback
  }

  const districts = districtsData?.data || [];

  return (
    <div className="min-h-screen bg-[#FAF8F5] dark:bg-slate-950 py-12 px-6 md:px-12 font-sans">
      <div className="max-w-[1320px] mx-auto space-y-10">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-[#0F5F58] dark:text-[#91D6CD] text-[11px] font-semibold uppercase tracking-widest mb-2">
              <MapPin className="w-3.5 h-3.5" />
              <span>Dữ liệu thị trường 55 khu vực TP.HCM</span>
            </div>
            <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-medium text-[#111827] dark:text-white tracking-tight">
              Khu vực &amp; Quận / Huyện
            </h1>
            <p className="text-sm text-[#6B7280] dark:text-slate-400 mt-2 max-w-xl font-sans">
              Khám phá tổng quan thị trường phòng trọ tại từng quận huyện. Giá trung vị và dải p25 – p75 tính từ tin đăng có giá hợp lệ.
            </p>
          </div>
        </div>

        {districts.length === 0 ? (
          <div className="bg-white dark:bg-[#1A2234] rounded-2xl border border-[#E7E2DA] dark:border-slate-800 p-12 text-center text-[#6B7280] text-sm">
            Không tìm thấy quận huyện phù hợp.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {districts.map((card) => (
              <DistrictCard key={card.id} card={card} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
