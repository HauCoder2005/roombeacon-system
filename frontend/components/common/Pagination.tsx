"use client";

import React from "react";
import type { PaginationMeta } from "@/lib/types/api";
import { formatNumber } from "@/lib/format";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface PaginationProps {
  meta?: PaginationMeta | null;
  onPageChange: (newPage: number) => void;
  className?: string;
}

export const Pagination: React.FC<PaginationProps> = ({
  meta,
  onPageChange,
  className = "",
}) => {
  if (!meta || meta.total_pages <= 1) return null;

  const { page, total_pages, total_items, per_page } = meta;
  const startItem = (page - 1) * per_page + 1;
  const endItem = Math.min(page * per_page, total_items);

  const getPageNumbers = () => {
    const pages: (number | string)[] = [];
    if (total_pages <= 7) {
      for (let i = 1; i <= total_pages; i++) pages.push(i);
    } else {
      pages.push(1);
      if (page > 3) pages.push("...");
      const start = Math.max(2, page - 1);
      const end = Math.min(total_pages - 1, page + 1);
      for (let i = start; i <= end; i++) {
        if (!pages.includes(i)) pages.push(i);
      }
      if (page < total_pages - 2) pages.push("...");
      pages.push(total_pages);
    }
    return pages;
  };

  return (
    <div
      className={`flex flex-col sm:flex-row items-center justify-between gap-4 py-6 border-t border-border ${className}`}
    >
      <div className="text-xs text-ink-muted">
        Hiển thị{" "}
        <strong className="text-ink font-semibold">{formatNumber(startItem)}</strong>–
        <strong className="text-ink font-semibold">{formatNumber(endItem)}</strong> trên{" "}
        <strong className="text-ink font-semibold">{formatNumber(total_items)}</strong> tin
      </div>

      <nav aria-label="Phân trang" className="flex items-center gap-1.5">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="p-2 rounded-xl border border-border text-xs font-medium text-ink hover:bg-bg disabled:opacity-40 disabled:pointer-events-none transition-colors"
          aria-label="Trang trước"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>

        {getPageNumbers().map((p, idx) => {
          if (p === "...") {
            return (
              <span key={idx} className="px-2 text-ink-muted text-xs select-none">
                …
              </span>
            );
          }
          const num = Number(p);
          const isCurrent = num === page;
          return (
            <button
              key={idx}
              type="button"
              onClick={() => onPageChange(num)}
              className={`w-9 h-9 rounded-xl text-xs font-semibold transition-colors ${
                isCurrent
                  ? "bg-brand text-white shadow-sm"
                  : "text-ink border border-border hover:bg-bg"
              }`}
              aria-current={isCurrent ? "page" : undefined}
            >
              {num}
            </button>
          );
        })}

        <button
          type="button"
          disabled={page >= total_pages}
          onClick={() => onPageChange(page + 1)}
          className="p-2 rounded-xl border border-border text-xs font-medium text-ink hover:bg-bg disabled:opacity-40 disabled:pointer-events-none transition-colors"
          aria-label="Trang sau"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </nav>
    </div>
  );
};
