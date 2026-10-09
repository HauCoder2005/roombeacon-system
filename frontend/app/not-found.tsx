import React from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { Compass, Home } from "lucide-react";

export const metadata: Metadata = {
  title: "404 — Không tìm thấy trang | RoomBeacon",
  description: "Trang không tồn tại trên hệ thống RoomBeacon.",
  robots: {
    index: false,
    follow: false,
  },
};

export default function NotFound() {
  return (
    <>
      <head>
        <meta name="robots" content="noindex" />
      </head>
      <div className="min-h-[70vh] flex flex-col items-center justify-center px-4 py-16 text-center">
        <div className="w-16 h-16 rounded-2xl bg-brand-soft text-brand flex items-center justify-center mb-4">
          <Compass className="w-8 h-8" />
        </div>
        <h1 className="text-3xl sm:text-4xl font-extrabold text-ink mb-2">
          404 — Không tìm thấy trang
        </h1>
        <p className="text-sm text-ink-muted max-w-md mb-6 leading-relaxed">
          Đường dẫn bạn truy cập có thể đã thay đổi hoặc không tồn tại trên hệ thống RoomBeacon.
        </p>
        <Link
          href="/"
          className="px-5 py-2.5 bg-brand text-white font-semibold text-sm rounded-xl hover:bg-brand-hover transition-colors flex items-center gap-2 shadow-sm"
        >
          <Home className="w-4 h-4" />
          <span>Về trang chủ</span>
        </Link>
      </div>
    </>
  );
}
