"use client";

import React, { useState } from "react";
import type { WardCard as WardCardType } from "@/lib/types/api";
import { WardCard } from "./WardCard";
import { Search, ArrowUpDown, Layers } from "lucide-react";

interface DistrictWardsListProps {
  initialWards: WardCardType[];
}

export const DistrictWardsList: React.FC<DistrictWardsListProps> = ({ initialWards }) => {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("-listing_count");

  const filtered = initialWards.filter((w) =>
    w.name.toLowerCase().includes(search.toLowerCase().trim())
  );

  filtered.sort((a, b) => {
    if (sort === "-listing_count") {
      return (b.stats.listing_count || 0) - (a.stats.listing_count || 0);
    }
    if (sort === "-median_price") {
      return (b.price.median || 0) - (a.price.median || 0);
    }
    if (sort === "median_price") {
      return (a.price.median || 0) - (b.price.median || 0);
    }
    return a.name.localeCompare(b.name, "vi");
  });

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-6">
        <div>
          <h2 className="text-xl sm:text-2xl font-bold text-ink flex items-center gap-2">
            <Layers className="w-5 h-5 text-brand" />
            <span>Danh sách phường trực thuộc</span>
          </h2>
          <p className="text-xs sm:text-sm text-ink-muted mt-0.5">
            Xem mức giá và mật độ tin đăng theo từng đơn vị phường
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative flex items-center">
            <Search className="w-3.5 h-3.5 text-ink-muted absolute left-3" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Lọc tên phường…"
              className="pl-8 pr-3 py-1.5 text-xs rounded-xl bg-surface border border-border focus:border-brand focus:ring-1 focus:ring-brand outline-none w-40 sm:w-48"
            />
          </div>

          <div className="flex items-center gap-1.5 bg-surface border border-border rounded-xl px-2.5 py-1.5">
            <ArrowUpDown className="w-3.5 h-3.5 text-brand" />
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value)}
              className="text-xs bg-transparent text-ink font-medium outline-none cursor-pointer"
            >
              <option value="-listing_count">Nhiều tin</option>
              <option value="-median_price">Giá cao</option>
              <option value="median_price">Giá thấp</option>
              <option value="name">Tên phường (A-Z)</option>
            </select>
          </div>
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="bg-surface rounded-2xl border border-border p-12 text-center text-ink-muted text-sm">
          Không tìm thấy phường phù hợp với từ khóa.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {filtered.map((ward) => (
            <WardCard key={ward.id} card={ward} />
          ))}
        </div>
      )}
    </div>
  );
};
