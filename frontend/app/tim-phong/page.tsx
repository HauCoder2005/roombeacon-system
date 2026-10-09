import React, { Suspense } from "react";
import type { Metadata } from "next";
import { SearchResultsView } from "@/components/search/SearchResultsView";

export const metadata: Metadata = {
  title: "Tìm phòng trọ TP.HCM — RoomBeacon",
  description:
    "Tìm kiếm phòng trọ, căn hộ thuê tại TP.HCM kèm phân tích giá trung vị thị trường thật.",
};

export default function SearchPage() {
  return (
    <Suspense
      fallback={
        <div className="max-w-7xl mx-auto p-8 text-center text-ink-muted">
          Đang tải kết quả tìm kiếm...
        </div>
      }
    >
      <SearchResultsView />
    </Suspense>
  );
}
