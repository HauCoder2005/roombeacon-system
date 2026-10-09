"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import type { ListingImage } from "@/lib/types/api";
import {
  ChevronLeft,
  ChevronRight,
  Maximize2,
  X,
  Building2,
  Camera,
  ShieldCheck,
  ImageIcon,
} from "lucide-react";

interface ListingGalleryProps {
  images: ListingImage[];
  title: string;
  source: string;
  className?: string;
}

export const ListingGallery: React.FC<ListingGalleryProps> = ({
  images,
  title,
  source,
  className = "",
}) => {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const touchStartXRef = useRef<number | null>(null);

  const hasImages = images && images.length > 0;
  const currentImage = hasImages ? images[selectedIndex] : null;

  const handlePrev = useCallback(() => {
    if (!hasImages) return;
    setSelectedIndex((prev) => (prev > 0 ? prev - 1 : images.length - 1));
  }, [hasImages, images?.length]);

  const handleNext = useCallback(() => {
    if (!hasImages) return;
    setSelectedIndex((prev) => (prev < images.length - 1 ? prev + 1 : 0));
  }, [hasImages, images?.length]);

  // Keyboard navigation for ←/→ and Escape for lightbox
  useEffect(() => {
    if (!hasImages) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        handlePrev();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        handleNext();
      } else if (e.key === "Escape" && lightboxOpen) {
        e.preventDefault();
        setLightboxOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [hasImages, handlePrev, handleNext, lightboxOpen]);

  // Touch swipe support for mobile
  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartXRef.current = e.touches[0].clientX;
  };

  const handleTouchEnd = (e: React.TouchEvent) => {
    if (touchStartXRef.current === null) return;
    const touchEndX = e.changedTouches[0].clientX;
    const diff = touchEndX - touchStartXRef.current;
    touchStartXRef.current = null;
    if (diff > 40) {
      handlePrev();
    } else if (diff < -40) {
      handleNext();
    }
  };

  // Rewrite /api/v1/ to /api/rb/ for image proxy
  const toRbUrl = (url: string) => url.replace(/^\/api\/v1\//, "/api/rb/");

  if (!hasImages) {
    return (
      <div className={`flex flex-col gap-3 ${className}`}>
        {/* Placeholder Hero Photo */}
        <div className="relative w-full aspect-[16/10] rounded-2xl overflow-hidden shadow-sm bg-[#FAF8F5] dark:bg-slate-900 border border-[#E7E2DA] dark:border-slate-800 flex flex-col items-center justify-center p-8 text-center">
          <Building2 className="w-16 h-16 text-[#0F5F58]/30 mb-3" />
          <h3 className="font-display text-lg font-medium text-[#111827] dark:text-white mb-1">
            Chưa có hình ảnh thực tế từ nguồn {source}
          </h3>
          <p className="text-xs text-[#6B7280] dark:text-slate-400 max-w-md leading-relaxed font-sans">
            Tin đăng chưa tải được ảnh hoặc tính năng ảnh đang tạm tắt. Mọi thông tin diện tích, biểu đồ và định giá AI đã được đối soát đầy đủ.
          </p>
        </div>
      </div>
    );
  }

  const currentProxyUrl = currentImage ? toRbUrl(currentImage.url) : "";
  const displayThumbnails = images.slice(0, 5);
  const remainingCount = Math.max(0, images.length - 5);

  return (
    <div className={`flex flex-col gap-3 ${className}`}>
      {/* Main Hero Photo (16:10 aspect ratio) */}
      <div
        className="relative w-full aspect-[16/10] rounded-2xl overflow-hidden shadow-sm bg-slate-950 border border-[#E7E2DA] dark:border-slate-800 group select-none cursor-pointer"
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
        onClick={() => setLightboxOpen(true)}
      >
        <img
          src={currentProxyUrl}
          alt={`${title} - ảnh ${currentImage?.position || selectedIndex + 1}`}
          loading="eager"
          decoding="async"
          className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-[1.02]"
        />

        {/* Top-left: Counter Pill */}
        <div className="absolute top-4 left-4 z-10 px-3 py-1 rounded-full bg-black/60 backdrop-blur-md text-white text-[11px] font-semibold tracking-wider uppercase pointer-events-none">
          {selectedIndex + 1} / {images.length} ẢNH
        </div>

        {/* Top-right: Architectural Verified Stamp */}
        <div className="absolute top-4 right-4 z-10 px-3 py-1 rounded-full bg-white/90 dark:bg-slate-900/90 backdrop-blur-md text-[#0F5F58] dark:text-[#91D6CD] text-[11px] font-semibold flex items-center gap-1 shadow-sm pointer-events-none">
          <ShieldCheck className="w-3.5 h-3.5 text-[#0F5F58]" />
          <span>Ảnh thực tế chuẩn RoomBeacon</span>
        </div>

        {/* Side Navigation Arrows */}
        {images.length > 1 && (
          <div className="absolute inset-y-0 inset-x-3 flex items-center justify-between pointer-events-none">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                handlePrev();
              }}
              aria-label="Ảnh trước"
              className="pointer-events-auto w-10 h-10 rounded-full bg-white/85 dark:bg-slate-900/85 backdrop-blur hover:bg-white text-[#111827] dark:text-white flex items-center justify-center shadow-md transition-all active:scale-95 cursor-pointer"
            >
              <ChevronLeft className="w-5 h-5" />
            </button>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                handleNext();
              }}
              aria-label="Ảnh tiếp theo"
              className="pointer-events-auto w-10 h-10 rounded-full bg-white/85 dark:bg-slate-900/85 backdrop-blur hover:bg-white text-[#111827] dark:text-white flex items-center justify-center shadow-md transition-all active:scale-95 cursor-pointer"
            >
              <ChevronRight className="w-5 h-5" />
            </button>
          </div>
        )}
      </div>

      {/* Thumbnails Row (Up to 5 items, matching design) */}
      {images.length > 1 && (
        <div className="grid grid-cols-5 gap-3">
          {displayThumbnails.map((img, idx) => {
            const isSelected = idx === selectedIndex;
            const isLastWithMore = idx === 4 && remainingCount > 0;

            return (
              <div
                key={img.position || idx}
                onClick={() => {
                  if (isLastWithMore) {
                    setLightboxOpen(true);
                  } else {
                    setSelectedIndex(idx);
                  }
                }}
                className={`cursor-pointer aspect-[4/3] rounded-xl overflow-hidden shadow-xs relative transition-all ${
                  isSelected && !isLastWithMore
                    ? "ring-2 ring-[#0F5F58] shadow-sm"
                    : "hover:ring-2 hover:ring-[#0F5F58]/50"
                }`}
              >
                <img
                  src={toRbUrl(img.url)}
                  alt={`${title} - thumb ${idx + 1}`}
                  loading="lazy"
                  decoding="async"
                  className="w-full h-full object-cover hover:opacity-90 transition-opacity"
                />

                {/* Last thumbnail overlay with +N */}
                {isLastWithMore && (
                  <div className="absolute inset-0 bg-[#0F5F58]/85 backdrop-blur-[2px] flex flex-col items-center justify-center text-white">
                    <span className="text-base font-bold">+{remainingCount + 1}</span>
                    <span className="text-[10px] uppercase font-semibold tracking-wider">Xem tất cả</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Lightbox Modal (Full Screen) */}
      {lightboxOpen && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 bg-black/95 backdrop-blur-md flex flex-col justify-between p-4 sm:p-6 select-none animate-fade-in"
          onClick={() => setLightboxOpen(false)}
        >
          {/* Lightbox Header */}
          <div className="flex items-center justify-between text-white w-full max-w-6xl mx-auto z-10 pb-2">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-sm sm:text-base truncate max-w-md">
                {title}
              </span>
              <span className="text-white/60 text-xs sm:text-sm">
                ({selectedIndex + 1}/{images.length})
              </span>
            </div>
            <button
              type="button"
              onClick={() => setLightboxOpen(false)}
              className="p-2 text-white/80 hover:text-white rounded-full bg-white/10 hover:bg-white/20 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Lightbox Main Image */}
          <div
            className="relative flex-1 flex items-center justify-center max-w-6xl mx-auto w-full my-auto overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <img
              src={currentProxyUrl}
              alt={`${title} - phóng to ${selectedIndex + 1}`}
              className="max-h-[82vh] max-w-full object-contain rounded-lg shadow-2xl"
            />

            {images.length > 1 && (
              <>
                <button
                  type="button"
                  onClick={handlePrev}
                  className="absolute left-2 top-1/2 -translate-y-1/2 w-11 h-11 rounded-full bg-white/20 hover:bg-white/40 text-white flex items-center justify-center backdrop-blur-md transition-all active:scale-95 cursor-pointer"
                >
                  <ChevronLeft className="w-6 h-6" />
                </button>
                <button
                  type="button"
                  onClick={handleNext}
                  className="absolute right-2 top-1/2 -translate-y-1/2 w-11 h-11 rounded-full bg-white/20 hover:bg-white/40 text-white flex items-center justify-center backdrop-blur-md transition-all active:scale-95 cursor-pointer"
                >
                  <ChevronRight className="w-6 h-6" />
                </button>
              </>
            )}
          </div>

          {/* Lightbox Thumbnails Bottom Bar */}
          <div
            className="flex justify-center gap-2 overflow-x-auto py-2 max-w-4xl mx-auto w-full no-scrollbar"
            onClick={(e) => e.stopPropagation()}
          >
            {images.map((img, idx) => (
              <button
                key={img.position || idx}
                type="button"
                onClick={() => setSelectedIndex(idx)}
                className={`relative w-14 h-10 shrink-0 rounded-md overflow-hidden transition-all ${
                  idx === selectedIndex
                    ? "ring-2 ring-[#B8892E] opacity-100 scale-105"
                    : "opacity-40 hover:opacity-80"
                }`}
              >
                <img
                  src={toRbUrl(img.url)}
                  alt={`thumbnail ${idx + 1}`}
                  className="w-full h-full object-cover"
                />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
