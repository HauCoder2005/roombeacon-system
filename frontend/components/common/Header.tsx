"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Calculator, Compass, Map, Search, TableProperties } from "lucide-react";
import { Logo } from "./Logo";

const NAV = [
  { href: "/tim-phong", label: "Tìm phòng", icon: Search },
  { href: "/khu-vuc", label: "Khu vực", icon: Map },
  { href: "/dinh-gia", label: "Định giá", icon: Calculator },
  { href: "/#bang-gia", label: "Bảng giá", icon: TableProperties },
];

function isActive(pathname: string, href: string): boolean {
  if (href.startsWith("/#")) return false;
  return pathname === href || pathname.startsWith(`${href}/`);
}

export const Header: React.FC = () => {
  const pathname = usePathname() ?? "/";
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <>
      <header
        className={`sticky top-0 z-50 w-full border-b transition-colors ${
          scrolled ? "bg-surface/95 backdrop-blur-md border-border" : "bg-surface/90 backdrop-blur-sm border-border-subtle"
        }`}
      >
        <div className="mx-auto flex h-[68px] max-w-[1320px] items-center justify-between px-5 sm:px-10">
          <Logo />
          <nav aria-label="Điều hướng chính" className="hidden md:flex items-center gap-1 text-[15px]">
            {NAV.map(({ href, label }) => {
              const active = isActive(pathname, href);
              return (
                <Link
                  key={href}
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={`relative rounded-full px-4 py-2 font-medium transition-colors ${
                    active ? "text-brand" : "text-ink-soft hover:text-brand"
                  }`}
                >
                  {label}
                  {active && <span className="absolute inset-x-4 -bottom-[13px] h-[2px] rounded-full bg-brand" aria-hidden />}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>

      {/* Mobile bottom navigation (design: trang chủ mobile) */}
      <nav
        aria-label="Điều hướng nhanh"
        className="md:hidden fixed inset-x-0 bottom-0 z-50 border-t border-border bg-surface/95 backdrop-blur-md pb-[env(safe-area-inset-bottom)]"
      >
        <ul className="grid grid-cols-4">
          {[{ href: "/", label: "Khám phá", icon: Compass }, ...NAV.slice(0, 3)].map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : isActive(pathname, href);
            return (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={`flex min-h-[56px] flex-col items-center justify-center gap-1 text-[11px] font-medium ${
                    active ? "text-brand" : "text-ink-muted"
                  }`}
                >
                  <Icon className="h-5 w-5" strokeWidth={1.6} aria-hidden />
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </>
  );
};
