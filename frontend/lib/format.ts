const vnNumberFormatter = new Intl.NumberFormat("vi-VN");

export function formatNumber(val: number | null | undefined): string {
  if (val === null || val === undefined) return "Chưa đủ dữ liệu";
  return vnNumberFormatter.format(val);
}

export function formatListingCount(val: number | null | undefined): string {
  if (val === null || val === undefined) return "Chưa đủ dữ liệu";
  return `${vnNumberFormatter.format(val)} tin`;
}

export function formatPrice(
  val: number | null | undefined,
  options?: { shortUnit?: boolean; perMonth?: boolean }
): string {
  if (val === null || val === undefined) return "Chưa đủ dữ liệu";
  if (val <= 0) return "Chưa đủ dữ liệu";

  const { shortUnit = false, perMonth = false } = options || {};

  if (val >= 1_000_000_000) {
    const ty = val / 1_000_000_000;
    const formatted = ty % 1 === 0 ? ty.toString() : ty.toFixed(1).replace(".", ",");
    const unit = "tỷ";
    return perMonth ? `${formatted} ${unit}/tháng` : `${formatted} ${unit}`;
  }

  if (val >= 1_000_000) {
    const tr = val / 1_000_000;
    const formatted = tr % 1 === 0 ? tr.toString() : tr.toFixed(1).replace(".", ",");
    const unit = shortUnit ? "tr" : "triệu";
    return perMonth ? `${formatted} ${unit}/tháng` : `${formatted} ${unit}`;
  }

  return `${vnNumberFormatter.format(val)} đ${perMonth ? "/tháng" : ""}`;
}

export function formatPricePerM2(val: number | null | undefined): string {
  if (val === null || val === undefined) return "Chưa đủ dữ liệu";
  return `${vnNumberFormatter.format(Math.round(val))} đ/m²`;
}

export function formatArea(val: number | null | undefined): string {
  if (val === null || val === undefined) return "Chưa đủ dữ liệu";
  const formatted = val % 1 === 0 ? val.toString() : val.toFixed(1).replace(".", ",");
  return `${formatted} m²`;
}

export function formatVietnamDateTime(isoString: string | null | undefined): string {
  if (!isoString) return "Chưa rõ";
  try {
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return "Chưa rõ";
    return new Intl.DateTimeFormat("vi-VN", {
      timeZone: "Asia/Ho_Chi_Minh",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  } catch {
    return "Chưa rõ";
  }
}

export function formatRelativeTime(isoString: string | null | undefined): string {
  if (!isoString) return "Mới đăng";
  try {
    const date = new Date(isoString);
    const now = new Date();
    const diffHours = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60));
    if (diffHours < 24) return "Hôm nay";
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays === 1) return "Hôm qua";
    return `${diffDays} ngày trước`;
  } catch {
    return "Mới đăng";
  }
}

export function formatWarning(warning: string): string {
  switch (warning) {
    case "area_outside_typical_range":
      return "Diện tích ngoài khoảng phổ biến (15–50 m²), ước tính kém chính xác hơn.";
    case "low_price_segment_less_accurate":
      return "Phân khúc giá thấp — model thường ước tính cao hơn thực tế.";
    case "high_price_segment_less_accurate":
      return "Phân khúc giá cao — model thường ước tính thấp hơn thực tế.";
    case "district_unknown_to_model":
    case "ward_unknown_to_model":
      return "Khu vực này có ít dữ liệu huấn luyện.";
    default:
      return warning;
  }
}
