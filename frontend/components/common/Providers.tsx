"use client";

import React, { useState, useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AlertTriangle, Info, CheckCircle2, X } from "lucide-react";
import type { ToastItem } from "@/lib/toast";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 5 * 60 * 1000,
            gcTime: 10 * 60 * 1000,
            retry: (failureCount, error: any) => {
              if (error?.code && error.code >= 400 && error.code < 500) {
                return false;
              }
              return failureCount < 2;
            },
            refetchOnWindowFocus: false,
          },
        },
      })
  );

  const [toasts, setToasts] = useState<ToastItem[]>([]);

  useEffect(() => {
    const handleToastEvent = (e: Event) => {
      const customEvent = e as CustomEvent<ToastItem>;
      if (customEvent.detail) {
        const newToast: ToastItem = {
          id: customEvent.detail.id || Math.random().toString(36).substring(2, 9),
          message: customEvent.detail.message,
          type: customEvent.detail.type || "info",
        };

        setToasts((prev) => [...prev, newToast]);

        // Auto remove after 5 seconds
        setTimeout(() => {
          setToasts((prev) => prev.filter((t) => t.id !== newToast.id));
        }, 5000);
      }
    };

    window.addEventListener("roombeacon:toast", handleToastEvent);
    return () => window.removeEventListener("roombeacon:toast", handleToastEvent);
  }, []);

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  return (
    <QueryClientProvider client={queryClient}>
      {children}

      {/* Global Toast Container */}
      <div
        className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 pointer-events-none max-w-sm w-full px-4 sm:px-0"
        aria-live="polite"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`pointer-events-auto p-4 rounded-2xl border shadow-xl flex items-center justify-between gap-3 text-sm font-semibold transition-all animate-in fade-in slide-in-from-bottom-5 duration-300 ${
              toast.type === "warning"
                ? "bg-amber-50 text-amber-900 border-amber-300 dark:bg-amber-950/90 dark:text-amber-200 dark:border-amber-700"
                : toast.type === "error"
                ? "bg-rose-50 text-rose-900 border-rose-300 dark:bg-rose-950/90 dark:text-rose-200 dark:border-rose-700"
                : toast.type === "success"
                ? "bg-emerald-50 text-emerald-900 border-emerald-300 dark:bg-emerald-950/90 dark:text-emerald-200 dark:border-emerald-700"
                : "bg-surface text-ink border-border dark:bg-slate-900"
            }`}
          >
            <div className="flex items-center gap-2.5">
              {toast.type === "warning" ? (
                <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0" />
              ) : toast.type === "error" ? (
                <AlertTriangle className="w-5 h-5 text-rose-600 dark:text-rose-400 shrink-0" />
              ) : toast.type === "success" ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400 shrink-0" />
              ) : (
                <Info className="w-5 h-5 text-brand shrink-0" />
              )}
              <span>{toast.message}</span>
            </div>
            <button
              onClick={() => removeToast(toast.id)}
              className="p-1 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 text-current transition-colors"
              aria-label="Đóng thông báo"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
    </QueryClientProvider>
  );
}
