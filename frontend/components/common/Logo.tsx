import React from "react";
import Link from "next/link";
import { BearMark } from "./BearMark";

interface LogoProps {
  className?: string;
  showTagline?: boolean;
}

export const Logo: React.FC<LogoProps> = ({ className = "", showTagline = false }) => {
  return (
    <Link
      href="/"
      className={`inline-flex items-center gap-2.5 group rounded-lg focus-visible:ring-2 focus-visible:ring-brand ${className}`}
      aria-label="RoomBeacon — Trang chủ"
    >
      <BearMark className="w-10 h-10 shrink-0 transition-transform duration-200 group-hover:-translate-y-0.5 motion-reduce:transition-none motion-reduce:group-hover:translate-y-0" />
      <span className="flex flex-col">
        <span className="font-display text-[22px] leading-none font-semibold tracking-tight">
          <span className="text-ink">Room</span>
          <span className="text-brand">Beacon</span>
        </span>
        {showTagline && (
          <span className="mt-1 text-[11px] font-medium text-ink-muted">Giá thuê minh bạch TP.HCM</span>
        )}
      </span>
    </Link>
  );
};
