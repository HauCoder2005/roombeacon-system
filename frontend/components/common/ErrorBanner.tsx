"use client";

import React, { useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { AlertTriangle, Clock, RefreshCw, ServerCrash, ShieldAlert } from "lucide-react";

interface ErrorBannerProps {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}

export const ErrorBanner: React.FC<ErrorBannerProps> = ({ error, onRetry, className = "" }) => {
  const [retryCountdown, setRetryCountdown] = useState<number | null>(null);

  const apiError = error instanceof ApiError ? error : null;
  const status = apiError?.code;
  const requestId = apiError?.envelope?.meta?.request_id;
  const message = apiError?.message || "Đã xảy ra lỗi không mong muốn.";

  useEffect(() => {
    if (status === 429 && apiError?.retryAfterSeconds) {
      setRetryCountdown(apiError.retryAfterSeconds);
      const timer = setInterval(() => {
        setRetryCountdown((prev) => {
          if (prev === null || prev <= 1) {
            clearInterval(timer);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
      return () => clearInterval(timer);
    }
  }, [status, apiError?.retryAfterSeconds]);

  useEffect(() => {
    if (status === 503 && onRetry) {
      setRetryCountdown(30);
      const timer = setInterval(() => {
        setRetryCountdown((prev) => {
          if (prev === null || prev <= 1) {
            clearInterval(timer);
            onRetry();
            return null;
          }
          return prev - 1;
        });
      }, 1000);
      return () => clearInterval(timer);
    }
  }, [status, onRetry]);

  if (!error) return null;

  if (status === 503) {
    return (
      <div
        role="alert"
        className={`w-full bg-amber-500/10 border border-amber-500/30 text-amber-900 dark:text-amber-200 p-4 rounded-xl flex items-start gap-3 ${className}`}
      >
        <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
        <div className="flex-1 text-sm">
          <p className="font-semibold text-amber-800 dark:text-amber-300">
            Dữ liệu tạm thời không khả dụng
          </p>
          <p className="text-amber-700/90 dark:text-amber-300/80 mt-0.5">
            Hệ thống đang chuẩn bị kết nối dữ liệu. Sẽ tự động thử lại sau{" "}
            {retryCountdown ?? 30} giây.
          </p>
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="px-3 py-1 bg-amber-500 text-white rounded-lg text-xs font-medium hover:bg-amber-600 transition-colors flex items-center gap-1.5 shrink-0"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Thử ngay
          </button>
        )}
      </div>
    );
  }

  if (status === 429) {
    return (
      <div
        role="alert"
        className={`w-full bg-blue-500/10 border border-blue-500/30 text-blue-900 dark:text-blue-200 p-4 rounded-xl flex items-start gap-3 ${className}`}
      >
        <Clock className="w-5 h-5 text-blue-500 shrink-0 mt-0.5" />
        <div className="flex-1 text-sm">
          <p className="font-semibold">Thao tác quá nhanh</p>
          <p className="text-blue-800 dark:text-blue-300 mt-0.5">
            Thử lại sau {retryCountdown !== null ? retryCountdown : 60} giây.
          </p>
        </div>
      </div>
    );
  }

  if (status === 401) {
    return (
      <div
        role="alert"
        className={`w-full bg-bad/10 border border-bad/30 text-bad p-4 rounded-xl flex items-start gap-3 ${className}`}
      >
        <ShieldAlert className="w-5 h-5 text-bad shrink-0 mt-0.5" />
        <div className="flex-1 text-sm">
          <p className="font-semibold">Phiên kết nối không hợp lệ</p>
          <p className="text-xs text-ink-muted mt-0.5">
            Lỗi cấu hình server (ROOMBEACON_API_KEY chưa hợp lệ).
          </p>
        </div>
      </div>
    );
  }

  if (status === 500 || (status && status >= 500)) {
    return (
      <div
        role="alert"
        className={`w-full bg-bad/10 border border-bad/30 text-bad p-4 rounded-xl flex items-start gap-3 ${className}`}
      >
        <ServerCrash className="w-5 h-5 text-bad shrink-0 mt-0.5" />
        <div className="flex-1 text-sm">
          <p className="font-semibold">Có lỗi xảy ra trên hệ thống</p>
          <p className="text-xs text-ink-muted mt-0.5">{message}</p>
          {requestId && (
            <p className="text-[11px] font-mono text-ink-muted mt-1">
              Mã yêu cầu (Request ID): <span className="underline select-all">{requestId}</span>
            </p>
          )}
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="px-3 py-1 bg-surface border border-border text-ink rounded-lg text-xs font-medium hover:bg-bg transition-colors flex items-center gap-1.5 shrink-0"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Thử lại
          </button>
        )}
      </div>
    );
  }

  return (
    <div
      role="alert"
      className={`w-full bg-slate-500/10 border border-slate-500/20 text-ink p-4 rounded-xl flex items-start gap-3 ${className}`}
    >
      <AlertTriangle className="w-5 h-5 text-ink-muted shrink-0 mt-0.5" />
      <div className="flex-1 text-sm">
        <p className="font-medium">{message}</p>
        {requestId && (
          <p className="text-[11px] font-mono text-ink-muted mt-0.5">
            ID: {requestId}
          </p>
        )}
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="px-3 py-1 bg-surface border border-border text-ink rounded-lg text-xs font-medium hover:bg-bg shrink-0"
        >
          Thử lại
        </button>
      )}
    </div>
  );
};
