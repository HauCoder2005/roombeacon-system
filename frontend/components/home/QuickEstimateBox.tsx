"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { DistrictCard } from "@/lib/types/api";
import { Sparkles, ArrowRight, Gauge, CheckCircle2 } from "lucide-react";

interface QuickEstimateBoxProps {
  districts: DistrictCard[];
}

export const QuickEstimateBox: React.FC<QuickEstimateBoxProps> = ({
  districts,
}) => {
  const router = useRouter();
  const [districtId, setDistrictId] = useState(districts[0]?.id || "");
  const [areaM2, setAreaM2] = useState<number>(25);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!districtId) return;
    router.push(`/dinh-gia?district_id=${districtId}&area=${areaM2}`);
  };

  return (
    <section className="px-6 md:px-12 my-12" id="quick-valuation">
      <div className="max-w-[1320px] mx-auto bg-[#0F5F58] rounded-[24px] text-white p-8 md:p-14 relative overflow-hidden shadow-xl">
        {/* Ambient Glow Behind CTA */}
        <div className="absolute -right-20 -bottom-20 w-96 h-96 bg-[#B8892E]/25 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -left-20 -top-20 w-80 h-80 bg-white/5 rounded-full blur-2xl pointer-events-none" />

        <div className="relative z-10 grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
          {/* Text Column */}
          <div className="lg:col-span-5 space-y-3">
            <span className="text-[11px] uppercase tracking-widest text-[#B8892E] font-semibold block">
              Công cụ phân tích AI
            </span>
            <h2 className="text-3xl sm:text-4xl font-display font-medium text-white tracking-tight leading-tight">
              Định giá phòng trong 10 giây
            </h2>
            <p className="text-sm sm:text-base text-white/80 leading-relaxed font-sans">
              Nhập khu vực và diện tích để nhận giá ước tính, khoảng giá và so sánh với giá trung vị khu vực.
            </p>
          </div>

          {/* Interactive Form Column */}
          <div className="lg:col-span-7 bg-white/10 backdrop-blur-md p-4 sm:p-5 rounded-2xl border border-white/20">
            <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row items-center gap-3">
              {/* District Select */}
              <div className="w-full sm:flex-1 relative">
                <label className="text-[10px] uppercase tracking-wider text-white/70 block mb-1 font-semibold">
                  Vị trí căn phòng
                </label>
                <select
                  value={districtId}
                  onChange={(e) => setDistrictId(e.target.value)}
                  className="w-full h-12 bg-white text-[#111827] rounded-xl px-3.5 text-sm font-semibold outline-none border border-transparent focus:border-[#B8892E] transition cursor-pointer"
                >
                  <option value="">Chọn Quận / Huyện…</option>
                  {districts.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Area Input */}
              <div className="w-full sm:w-36 relative">
                <label className="text-[10px] uppercase tracking-wider text-white/70 block mb-1 font-semibold">
                  Diện tích (m²)
                </label>
                <input
                  type="number"
                  min={10}
                  max={120}
                  value={areaM2}
                  onChange={(e) => setAreaM2(Number(e.target.value))}
                  placeholder="25 m²"
                  className="w-full h-12 bg-white text-[#111827] rounded-xl px-3.5 text-sm font-semibold outline-none border border-transparent focus:border-[#B8892E] placeholder-[#9CA3AF] transition"
                />
              </div>

              {/* Submit Button */}
              <div className="w-full sm:w-auto self-end">
                <button
                  type="submit"
                  className="w-full sm:w-auto h-12 px-7 rounded-xl bg-[#B8892E] hover:bg-[#a07424] active:scale-[0.98] text-white text-sm font-semibold transition-all shadow-md flex items-center justify-center gap-2 whitespace-nowrap cursor-pointer"
                >
                  <span>Định giá ngay</span>
                  <Gauge className="w-4 h-4 stroke-[2.5]" />
                </button>
              </div>
            </form>

            <div className="mt-3 flex items-center justify-between text-xs text-white/70 px-1">
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-[#B8892E]" />
                Ước tính tham khảo từ mô hình thử nghiệm
              </span>
              <span>Kết quả kèm khoảng giá và cảnh báo</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
