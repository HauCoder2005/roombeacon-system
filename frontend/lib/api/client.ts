import type {
  ApiEnvelope,
  DistrictCard,
  WardCard,
  ResolveChoices,
  ResolveResult,
  ListingCard,
  ListingDetail,
  PricePoint,
  PriceEstimate,
  ModelCard,
  MarketSummary,
  MarketDay,
  ListingQueryParams,
} from "../types/api";

export class ApiError extends Error {
  code: number;
  envelope?: ApiEnvelope<unknown>;
  retryAfterSeconds?: number;

  constructor(
    message: string,
    code: number,
    envelope?: ApiEnvelope<unknown>,
    retryAfterSeconds?: number
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.envelope = envelope;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

const BFF_BASE = "/api/rb";

export async function apiClient<T>(
  path: string,
  options?: RequestInit
): Promise<ApiEnvelope<T>> {
  const cleanPath = path.startsWith("/") ? path.slice(1) : path;
  const url = `${BFF_BASE}/${cleanPath}`;

  const response = await fetch(url, {
    ...options,
    headers: {
      Accept: "application/json",
      ...options?.headers,
    },
  });

  const retryAfterHeader = response.headers.get("Retry-After");
  const retryAfterSeconds = retryAfterHeader
    ? parseInt(retryAfterHeader, 10)
    : undefined;

  let body: ApiEnvelope<T> | null = null;
  const contentType = response.headers.get("content-type");
  if (contentType && contentType.includes("application/json")) {
    try {
      body = (await response.json()) as ApiEnvelope<T>;
    } catch {
      // ignore json parse error
    }
  }

  // 300 Multiple Choices is valid payload for ward resolve
  if (response.status === 300 && body) {
    return body;
  }

  if (!response.ok) {
    const retrySec = retryAfterSeconds || 60;
    if (response.status === 429 && typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("roombeacon:toast", {
          detail: {
            id: Math.random().toString(36).substring(2, 9),
            message: `Thử lại sau ${retrySec} giây`,
            type: "warning",
          },
        })
      );
    }

    const message =
      body?.message ||
      (response.status === 401
        ? "Phiên kết nối không hợp lệ"
        : response.status === 404
        ? "Không tìm thấy dữ liệu"
        : response.status === 429
        ? `Thử lại sau ${retrySec} giây`
        : response.status === 503
        ? "Dữ liệu tạm thời không khả dụng"
        : `Lỗi kết nối (${response.status})`);

    throw new ApiError(
      message,
      response.status,
      body || undefined,
      retryAfterSeconds
    );
  }

  if (!body) {
    throw new ApiError("Phản hồi máy chủ không hợp lệ", response.status);
  }

  return body;
}

export async function getClientDistricts(params?: {
  q?: string;
  sort?: string;
  page?: number;
  per_page?: number;
}): Promise<ApiEnvelope<DistrictCard[]>> {
  const searchParams = new URLSearchParams();
  if (params?.q) searchParams.set("q", params.q);
  if (params?.sort) searchParams.set("sort", params.sort);
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.per_page) searchParams.set("per_page", String(params.per_page));

  const queryStr = searchParams.toString();
  return apiClient<DistrictCard[]>(
    `locations/districts${queryStr ? `?${queryStr}` : ""}`
  );
}

export async function getClientDistrict(
  districtId: string
): Promise<ApiEnvelope<DistrictCard>> {
  return apiClient<DistrictCard>(`locations/districts/${districtId}`);
}

export async function getClientDistrictWards(
  districtId: string,
  params?: { q?: string; sort?: string; page?: number; per_page?: number }
): Promise<ApiEnvelope<WardCard[]>> {
  const searchParams = new URLSearchParams();
  if (params?.q) searchParams.set("q", params.q);
  if (params?.sort) searchParams.set("sort", params.sort);
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.per_page) searchParams.set("per_page", String(params.per_page));

  const queryStr = searchParams.toString();
  return apiClient<WardCard[]>(
    `locations/districts/${districtId}/wards${queryStr ? `?${queryStr}` : ""}`
  );
}

export async function resolveClientWard(
  ward: string,
  districtId?: string
): Promise<ResolveResult> {
  const searchParams = new URLSearchParams();
  searchParams.set("ward", ward);
  if (districtId) searchParams.set("district_id", districtId);

  try {
    const res = await apiClient<WardCard | ResolveChoices>(
      `locations/resolve?${searchParams.toString()}`
    );

    if (res.code === 200 && res.data) {
      return { type: "single", ward: res.data as WardCard };
    }
    if (res.code === 300 && res.data) {
      const choicesData = res.data as ResolveChoices;
      return { type: "choices", choices: choicesData.choices || [] };
    }
    return { type: "not_found" };
  } catch (err) {
    if (err instanceof ApiError && err.code === 404) {
      return { type: "not_found" };
    }
    throw err;
  }
}

export async function getClientListings(
  params?: ListingQueryParams
): Promise<ApiEnvelope<ListingCard[]>> {
  const searchParams = new URLSearchParams();
  if (params?.district_id) searchParams.set("district_id", params.district_id);
  if (params?.ward_id) searchParams.set("ward_id", params.ward_id);
  if (params?.q) searchParams.set("q", params.q);
  if (params?.price_min !== undefined)
    searchParams.set("price_min", String(params.price_min));
  if (params?.price_max !== undefined)
    searchParams.set("price_max", String(params.price_max));
  if (params?.area_min !== undefined)
    searchParams.set("area_min", String(params.area_min));
  if (params?.area_max !== undefined)
    searchParams.set("area_max", String(params.area_max));
  if (params?.intent) searchParams.set("intent", params.intent);
  if (params?.include_duplicates !== undefined)
    searchParams.set("include_duplicates", String(params.include_duplicates));
  if (params?.sort) searchParams.set("sort", params.sort);
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.per_page) searchParams.set("per_page", String(params.per_page));

  const queryStr = searchParams.toString();
  return apiClient<ListingCard[]>(`listings${queryStr ? `?${queryStr}` : ""}`);
}

export async function getClientListing(
  id: string
): Promise<ApiEnvelope<ListingDetail>> {
  return apiClient<ListingDetail>(`listings/${id}`);
}

export async function getClientListingPriceHistory(
  id: string
): Promise<ApiEnvelope<PricePoint[]>> {
  return apiClient<PricePoint[]>(`listings/${id}/price-history`);
}

export async function postClientPriceEstimate(body: {
  area_m2: number;
  district_id: string;
  ward_id?: string;
}): Promise<ApiEnvelope<PriceEstimate>> {
  return apiClient<PriceEstimate>("price-estimates", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
}

export async function getClientModelCard(): Promise<ApiEnvelope<ModelCard>> {
  return apiClient<ModelCard>("price-estimates/model");
}

export async function getClientMarketSummary(
  districtId?: string
): Promise<ApiEnvelope<MarketSummary>> {
  const searchParams = new URLSearchParams();
  if (districtId) searchParams.set("district_id", districtId);
  const q = searchParams.toString();
  return apiClient<MarketSummary>(`market/summary${q ? `?${q}` : ""}`);
}

export async function getClientMarketDaily(
  districtId?: string,
  dateFrom: string = "2026-09-23",
  dateTo?: string
): Promise<ApiEnvelope<MarketDay[]>> {
  const searchParams = new URLSearchParams();
  if (districtId) searchParams.set("district_id", districtId);
  if (dateFrom) searchParams.set("date_from", dateFrom);
  if (dateTo) searchParams.set("date_to", dateTo);
  const q = searchParams.toString();
  return apiClient<MarketDay[]>(`market/daily${q ? `?${q}` : ""}`);
}
