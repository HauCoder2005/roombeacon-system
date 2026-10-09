"use client";

import React from "react";
import { useModelCard } from "@/lib/api/hooks";
import { formatNumber, formatVietnamDateTime, formatPrice } from "@/lib/format";
import { X, Cpu, ShieldAlert, Sparkles, CheckCircle2 } from "lucide-react";

interface ModelCardDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ModelCardDrawer: React.FC<ModelCardDrawerProps> = ({
  isOpen,
  onClose,
}) => {
  const { data: res, isLoading, error } = useModelCard();
  const model = res?.data;

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/50 backdrop-blur-sm animate-in fade-in duration-200">
      <div
        className="bg-surface rounded-2xl border border-border shadow-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto p-6 relative"
        role="dialog"
        aria-modal="true"
        aria-labelledby="model-card-title"
      >
        <button
          onClick={onClose}
          className="absolute top-5 right-5 p-2 rounded-full hover:bg-bg text-ink-muted hover:text-ink transition-colors"
          aria-label="Đóng"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-2 text-brand mb-2">
          <Cpu className="w-5 h-5" />
          <span className="text-xs font-bold uppercase tracking-wider">
            Thẻ thông tin mô hình
          </span>
        </div>

        <h3 id="model-card-title" className="text-xl font-bold text-ink mb-1">
          LightGBM Champion (F4 RAW)
        </h3>
        <p className="text-xs text-ink-muted mb-4">
          Mô hình máy học dự đoán giá thuê phòng trọ được tinh chỉnh trên tập dữ liệu TP.HCM
        </p>

        {isLoading ? (
          <div className="space-y-3 py-6 animate-pulse">
            <div className="h-6 bg-slate-200 dark:bg-slate-700 rounded w-1/2" />
            <div className="h-16 bg-slate-200 dark:bg-slate-700 rounded" />
            <div className="h-16 bg-slate-200 dark:bg-slate-700 rounded" />
          </div>
        ) : error || !model ? (
          <div className="p-4 bg-rose-50 text-bad rounded-xl text-sm mb-4">
            Không thể tải thông tin mô hình lúc này.
          </div>
        ) : (
          <div className="space-y-4 text-sm">
            {/* Status & ID */}
            <div className="p-3 bg-brand-soft/40 dark:bg-brand/10 border border-brand/20 rounded-xl">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-ink-muted">Mã mô hình:</span>
                <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-beacon/20 text-beacon border border-beacon/30">
                  {model.readiness === "experimental" ? "Thử nghiệm" : "Chính thức"}
                </span>
              </div>
              <div className="text-xs font-mono text-ink truncate select-all">
                {model.model_id}
              </div>
            </div>

            {/* Metrics */}
            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 bg-bg dark:bg-slate-800/60 border border-border rounded-xl">
                <div className="text-xs text-ink-muted mb-0.5">Sai số tuyệt đối trung vị (Median AE)</div>
                <div className="text-lg font-bold text-ink">
                  {formatPrice(model.test_metrics.median_ae)}
                </div>
                <div className="text-[11px] text-ink-muted">50% tin có sai số dưới mức này</div>
              </div>
              <div className="p-3 bg-bg dark:bg-slate-800/60 border border-border rounded-xl">
                <div className="text-xs text-ink-muted mb-0.5">Sai số tuyệt đối trung bình (MAE)</div>
                <div className="text-lg font-bold text-ink">
                  {formatPrice(model.test_metrics.mae)}
                </div>
                <div className="text-[11px] text-ink-muted">Hệ số R²: {model.test_metrics.r2 ?? "N/A"}</div>
              </div>
            </div>

            {/* Scope / Ranges */}
            <div className="p-3 bg-bg dark:bg-slate-800/60 border border-border rounded-xl space-y-2">
              <div className="font-semibold text-xs text-ink flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-beacon" />
                Phạm vi tối ưu của mô hình
              </div>
              <div className="flex justify-between text-xs py-1 border-b border-border/50">
                <span className="text-ink-muted">Diện tích tin cậy:</span>
                <span className="font-medium text-ink">
                  {model.typical_area_range.low} – {model.typical_area_range.high} m²
                </span>
              </div>
              <div className="flex justify-between text-xs py-1 border-b border-border/50">
                <span className="text-ink-muted">Phân khúc giá tin cậy:</span>
                <span className="font-medium text-ink">
                  {formatPrice(model.reliable_price_range.low)} – {formatPrice(model.reliable_price_range.high)}
                </span>
              </div>
              <div className="flex justify-between text-xs py-1">
                <span className="text-ink-muted">Thời điểm hoàn tất huấn luyện:</span>
                <span className="font-medium text-ink">
                  {formatVietnamDateTime(model.trained_until)}
                </span>
              </div>
            </div>

            {/* Notice */}
            <div className="p-3 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-xl flex gap-2.5 text-xs text-amber-800 dark:text-amber-300">
              <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <strong>Lưu ý trách nhiệm:</strong> Mô hình được tạo ra với mục tiêu hỗ trợ người tìm phòng tham khảo mức giá hợp lý. Khoảng giá dự đoán bao trùm khoảng 50% tin đăng trong tập kiểm thử. Không dùng làm căn cứ pháp lý hoặc quyết định giao dịch độc lập.
              </div>
            </div>
          </div>
        )}

        <div className="mt-6 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-semibold text-ink bg-bg hover:bg-slate-200 dark:hover:bg-slate-800 rounded-xl transition-colors"
          >
            Đã hiểu & Đóng
          </button>
        </div>
      </div>
    </div>
  );
};
