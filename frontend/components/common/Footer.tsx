import React from "react";
import Link from "next/link";
import { Logo } from "./Logo";
import { getServerDistricts } from "@/lib/api/server";
import { formatVietnamDateTime } from "@/lib/format";

async function latestSnapshot(): Promise<{ snapshot_id: string; loaded_at: string } | null> {
  try {
    const res = await getServerDistricts({ per_page: 1 });
    return res.meta?.data_snapshot ?? null;
  } catch {
    return null;
  }
}

export async function Footer() {
  const snapshot = await latestSnapshot();

  return (
    <footer className="mt-auto border-t border-border bg-bg-alt pb-[72px] md:pb-0">
      <div className="mx-auto grid max-w-[1320px] gap-10 px-5 py-12 sm:px-10 md:grid-cols-[1.4fr_1fr_1fr]">
        <div className="space-y-3">
          <Logo showTagline />
          <p className="max-w-sm text-[13px] leading-relaxed text-ink-muted">
            RoomBeacon tổng hợp tin cho thuê công khai tại TP.HCM, làm sạch dữ liệu và công bố giá thị trường theo
            quận, phường. Chúng tôi không phải bên cho thuê và không hiển thị thông tin liên hệ của người đăng.
          </p>
        </div>
        <div>
          <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink">Khám phá</h2>
          <ul className="space-y-2 text-[14px] text-ink-soft">
            <li><Link className="hover:text-brand" href="/tim-phong">Tìm phòng</Link></li>
            <li><Link className="hover:text-brand" href="/khu-vuc">Giá theo khu vực</Link></li>
            <li><Link className="hover:text-brand" href="/#bang-gia">Bảng giá thuê</Link></li>
            <li><Link className="hover:text-brand" href="/dinh-gia">Định giá phòng</Link></li>
          </ul>
        </div>
        <div>
          <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink">Dữ liệu</h2>
          <dl className="space-y-2 text-[13px] text-ink-muted">
            <div>
              <dt className="inline">Cập nhật: </dt>
              <dd className="inline font-medium text-ink-soft">
                {snapshot ? formatVietnamDateTime(snapshot.loaded_at) : "Chưa có dữ liệu"}
              </dd>
            </div>
            {snapshot && (
              <div>
                <dt className="inline">Snapshot: </dt>
                <dd className="inline font-mono text-[12px]">{snapshot.snapshot_id.slice(0, 8)}</dd>
              </div>
            )}
            <div>Định giá là ước tính tham khảo từ mô hình thử nghiệm.</div>
          </dl>
        </div>
      </div>
      <div className="border-t border-border-subtle">
        <p className="mx-auto max-w-[1320px] px-5 py-5 text-[12px] text-ink-subtle sm:px-10">
          © {new Date().getFullYear()} RoomBeacon
        </p>
      </div>
    </footer>
  );
}
