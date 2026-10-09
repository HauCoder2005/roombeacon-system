import React from "react";
import { BarChart3, RefreshCw, ShieldCheck, Sparkles, Building, Lock } from "lucide-react";

export const WhyRoomBeacon: React.FC = () => {
  const features = [
    {
      icon: BarChart3,
      title: "Minh bạch hóa phân vị thị trường",
      desc: "Nắm rõ dải giá P25–P75 và giá trung vị chuẩn cho từng khu vực trước khi đi xem thực tế, tránh các tin giá ảo hoặc bị kê giá.",
    },
    {
      icon: RefreshCw,
      title: "Dữ liệu cập nhật định kỳ",
      desc: "Tin đăng công khai được thu thập định kỳ, làm sạch và chuẩn hóa giá, diện tích, quận phường trước khi tính thống kê.",
    },
    {
      icon: Lock,
      title: "Không lộ thông tin người đăng",
      desc: "RoomBeacon không hiển thị số điện thoại hay thông tin liên hệ; bạn xem tin gốc trên trang đăng ban đầu.",
    },
  ];

  return (
    <section className="py-20 bg-white dark:bg-[#1A2234] border-t border-[#E7E2DA] dark:border-slate-800">
      <div className="max-w-[1320px] mx-auto px-6 md:px-12">
        <div className="text-center max-w-2xl mx-auto mb-14">
          <span className="text-[11px] font-semibold text-[#0F5F58] dark:text-[#91D6CD] uppercase tracking-widest block mb-2">
            Cách RoomBeacon làm việc
          </span>
          <h2 className="text-3xl sm:text-4xl font-display font-medium text-[#111827] dark:text-white tracking-tight">
            Vì sao nên chọn RoomBeacon?
          </h2>
          <p className="text-sm text-[#6B7280] dark:text-slate-400 mt-2 font-sans">
            Giá thuê minh bạch, tính từ dữ liệu thật
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {features.map((feat, idx) => (
            <div
              key={idx}
              className="p-8 rounded-[20px] bg-[#FAF8F5] dark:bg-slate-900/60 border border-[#E7E2DA] dark:border-slate-800 flex flex-col items-start transition-all hover:shadow-[0_10px_30px_rgba(17,24,39,0.04)]"
            >
              <div className="w-12 h-12 rounded-2xl bg-[#0F5F58]/10 text-[#0F5F58] dark:text-[#91D6CD] flex items-center justify-center mb-5">
                <feat.icon className="w-6 h-6 stroke-[1.8]" />
              </div>
              <h3 className="text-lg font-bold text-[#111827] dark:text-white mb-2 font-sans">
                {feat.title}
              </h3>
              <p className="text-sm text-[#6B7280] dark:text-slate-400 leading-relaxed font-sans">
                {feat.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
