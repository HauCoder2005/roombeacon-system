"use client";

import React, { useState } from "react";
import { ExternalLink, Copy, Check } from "lucide-react";

interface ListingActionBarProps {
  sourceUrl?: string | null;
  sourceName?: string;
  listingId: string | number;
}

export const ListingActionBar: React.FC<ListingActionBarProps> = ({
  sourceUrl,
  sourceName = "trang nguồn",
  listingId,
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopyLink = () => {
    if (typeof window !== "undefined") {
      navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    }
  };

  return (
    <div className="flex flex-col gap-2.5 pt-2">
      {/* Big Champagne Gold Primary Button */}
      {sourceUrl ? (
        <a
          href={sourceUrl}
          target="_blank"
          rel="noopener noreferrer nofollow"
          className="w-full py-3.5 px-6 rounded-full bg-[#B8892E] hover:bg-[#a07424] text-white font-semibold text-sm shadow-md hover:shadow-lg transition-all flex items-center justify-center gap-2 active:scale-[0.99] cursor-pointer"
        >
          <span>Xem tin gốc trên {sourceName}</span>
          <ExternalLink className="w-4 h-4 stroke-[2.5]" />
        </a>
      ) : (
        <div className="p-3 bg-[#FAF8F5] dark:bg-slate-900 rounded-xl text-center text-xs text-[#6B7280]">
          Tin lưu trữ — không có liên kết trang ngoài
        </div>
      )}

      {/* Secondary Outline Action: Copy Link */}
      <button
        type="button"
        onClick={handleCopyLink}
        className="w-full py-3 px-6 rounded-full bg-[#FAF8F5] dark:bg-slate-900 hover:bg-[#E7E2DA] dark:hover:bg-slate-800 text-[#0F5F58] dark:text-[#91D6CD] font-semibold text-xs transition-all flex items-center justify-center gap-2 border border-[#E7E2DA] dark:border-slate-800 cursor-pointer"
      >
        {copied ? (
          <>
            <Check className="w-4 h-4 text-[#047857]" />
            <span className="text-[#047857]">Đã sao chép liên kết!</span>
          </>
        ) : (
          <>
            <Copy className="w-4 h-4" />
            <span>Sao chép liên kết thẩm định</span>
          </>
        )}
      </button>
    </div>
  );
};
