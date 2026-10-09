import React, { Suspense } from "react";
import type { Metadata } from "next";
import { EstimateForm } from "@/components/estimate/EstimateForm";
import { Sparkles, ShieldCheck, TrendingUp } from "lucide-react";

export const metadata: Metadata = {
  title: "Định giá phòng trọ — RoomBeacon",
  description:
    "Ước tính khoảng giá thuê phòng trọ hợp lý tại TP.HCM dựa trên mô hình máy học và phân tích mặt bằng thị trường thực tế.",
};

export default function EstimatePage() {
  return (
    <div className="min-h-screen py-12 px-6 md:px-12 bg-[#FAF8F5] dark:bg-slate-950 font-sans">
      <div className="max-w-[1320px] mx-auto space-y-10">
        {/* Header Hero */}
        <div className="text-center space-y-3 max-w-3xl mx-auto">
          <div className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-semibold bg-[#0F5F58]/10 text-[#0F5F58] dark:text-[#91D6CD] uppercase tracking-wider">
            <Sparkles className="w-3.5 h-3.5 text-[#B8892E]" />
            <span>Phân tích định giá thông minh AI</span>
          </div>
          <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-medium text-[#111827] dark:text-white tracking-tight">
            Định giá phòng trọ tại TP.HCM
          </h1>
          <p className="text-sm sm:text-base text-[#6B7280] dark:text-slate-400 max-w-2xl mx-auto leading-relaxed font-sans">
            Nhập diện tích và khu vực để nhận giá ước tính tham khảo, khoảng giá và vị trí so với thị trường khu vực.
          </p>
        </div>

        {/* Interactive 2-Column Parameter & Result Workspace */}
        <Suspense
          fallback={
            <div className="bg-white dark:bg-[#1A2234] rounded-2xl border border-[#E7E2DA] dark:border-slate-800 p-8 animate-pulse space-y-4">
              <div className="h-6 bg-slate-200 dark:bg-slate-700 rounded w-1/3" />
              <div className="h-14 bg-slate-200 dark:bg-slate-700 rounded" />
              <div className="h-14 bg-slate-200 dark:bg-slate-700 rounded" />
            </div>
          }
        >
          <EstimateForm />
        </Suspense>

        {/* Value Props & Explanations */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-10 border-t border-[#E7E2DA] dark:border-slate-800">
          <div className="p-6 rounded-[20px] bg-white dark:bg-[#1A2234] border border-[#E7E2DA] dark:border-slate-800 shadow-xs">
            <div className="w-10 h-10 rounded-xl bg-[#0F5F58]/10 text-[#0F5F58] flex items-center justify-center mb-4">
              <Sparkles className="w-5 h-5 text-[#B8892E]" />
            </div>
            <h4 className="font-display text-base font-bold text-[#111827] dark:text-white mb-1.5">
              Mô hình máy học thử nghiệm
            </h4>
            <p className="text-xs text-[#6B7280] dark:text-slate-400 leading-relaxed font-sans">
              Dự báo dựa trên thuật toán LightGBM chuẩn hóa, huấn luyện trên tập dữ liệu tin đăng đã làm sạch toàn TP.HCM.
            </p>
          </div>

          <div className="p-6 rounded-[20px] bg-white dark:bg-[#1A2234] border border-[#E7E2DA] dark:border-slate-800 shadow-xs">
            <div className="w-10 h-10 rounded-xl bg-[#0F5F58]/10 text-[#0F5F58] flex items-center justify-center mb-4">
              <TrendingUp className="w-5 h-5 text-[#0F5F58]" />
            </div>
            <h4 className="font-display text-base font-bold text-[#111827] dark:text-white mb-1.5">
              Đối chiếu phân vị khu vực
            </h4>
            <p className="text-xs text-[#6B7280] dark:text-slate-400 leading-relaxed font-sans">
              Mỗi kết quả đều đặt trong phổ giá thực tế (P25 – P75) của chính khu vực bạn chọn để xác định vị trí tương đối.
            </p>
          </div>

          <div className="p-6 rounded-[20px] bg-white dark:bg-[#1A2234] border border-[#E7E2DA] dark:border-slate-800 shadow-xs">
            <div className="w-10 h-10 rounded-xl bg-[#0F5F58]/10 text-[#0F5F58] flex items-center justify-center mb-4">
              <ShieldCheck className="w-5 h-5 text-[#0F5F58]" />
            </div>
            <h4 className="font-display text-base font-bold text-[#111827] dark:text-white mb-1.5">
              Cảnh báo miền tin cậy
            </h4>
            <p className="text-xs text-[#6B7280] dark:text-slate-400 leading-relaxed font-sans">
              Tự động phát hiện diện tích ngoại lai hoặc mẫu dữ liệu thưa thớt để thông báo độ tin cậy tương ứng cho người xem.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
