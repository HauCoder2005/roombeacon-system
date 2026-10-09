"use client";

import React, { useEffect } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Redacted structured error logging
  }, [error]);

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center p-6 text-center">
      <div className="w-14 h-14 rounded-2xl bg-bad/10 text-bad flex items-center justify-center mb-4">
        <AlertTriangle className="w-7 h-7" />
      </div>
      <h2 className="text-2xl font-bold text-ink mb-2">Đã xảy ra sự cố</h2>
      <p className="text-sm text-ink-muted max-w-md mb-6">
        Hệ thống không thể tải dữ liệu vào lúc này. Vui lòng thử lại.
      </p>
      {error?.digest && (
        <p className="text-xs font-mono text-ink-muted mb-4">
          Mã sự cố: {error.digest}
        </p>
      )}
      <button
        type="button"
        onClick={() => reset()}
        className="px-5 py-2.5 bg-brand text-white font-semibold text-sm rounded-xl hover:bg-brand-hover transition-colors flex items-center gap-2 shadow-sm"
      >
        <RefreshCw className="w-4 h-4" />
        <span>Thử lại</span>
      </button>
    </div>
  );
}
