import "server-only";
import type {
  ApiEnvelope,
  DistrictCard,
  WardCard,
  ResolveChoices,
  ResolveResult,
  ListingCard,
  ListingDetail,
  ListingImage,
  PricePoint,
  MarketSummary,
  MarketDay,
  ModelCard,
  ListingQueryParams,
} from "../types/api";

const BACKEND_URL = process.env.ROOMBEACON_API_URL || "http://127.0.0.1:8000";
const API_KEY = process.env.ROOMBEACON_API_KEY || "";
const REVALIDATE_SEC = Number(process.env.REVALIDATE_SECONDS || "300");

const BACKEND_TIMEOUT_MS = 10_000;

async function fetchFromBackend<T>(
  endpoint: string,
  tags: string[] = []
): Promise<ApiEnvelope<T>> {
  const url = `${BACKEND_URL}/api/v1/${endpoint.replace(/^\//, "")}`;
  const response = await fetch(url, {
    headers: {
      "X-API-Key": API_KEY,
      Accept: "application/json",
    },
    next: {
      revalidate: REVALIDATE_SEC,
      tags,
    },
    // A hung backend must not hold server renders open indefinitely.
    signal: AbortSignal.timeout(BACKEND_TIMEOUT_MS),
  });

  if (response.status === 300) {
    const data = (await response.json()) as ApiEnvelope<T>;
    return data;
  }

  if (!response.ok) {
    let errBody: any = null;
    try {
      errBody = await response.json();
    } catch {
      // not json
    }
    const message =
      errBody?.message || `Lỗi tải dữ liệu từ máy chủ (${response.status})`;
    throw new Error(message);
  }

  return response.json();
}

export async function getServerDistricts(params?: {
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
  const res = await fetchFromBackend<DistrictCard[]>(
    `locations/districts${queryStr ? `?${queryStr}` : ""}`,
    ["districts"]
  );

  if (res.data) {
    res.data = res.data.map((d) => ({
      ...d,
      cover_image: d.cover_image ?? null,
    }));
  }

  return res;
}

export async function getServerDistrict(
  districtId: string
): Promise<ApiEnvelope<DistrictCard>> {
  const res = await fetchFromBackend<DistrictCard>(
    `locations/districts/${districtId}`,
    [`district-${districtId}`]
  );
  if (res.data) {
    res.data = {
      ...res.data,
      cover_image: res.data.cover_image ?? null,
    };
  }
  return res;
}

export async function getServerDistrictWards(
  districtId: string,
  params?: { q?: string; sort?: string; page?: number; per_page?: number }
): Promise<ApiEnvelope<WardCard[]>> {
  const searchParams = new URLSearchParams();
  if (params?.q) searchParams.set("q", params.q);
  if (params?.sort) searchParams.set("sort", params.sort);
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.per_page) searchParams.set("per_page", String(params.per_page));

  const queryStr = searchParams.toString();
  const res = await fetchFromBackend<WardCard[]>(
    `locations/districts/${districtId}/wards${queryStr ? `?${queryStr}` : ""}`,
    [`wards-${districtId}`]
  );
  if (res.data) {
    res.data = res.data.map((w) => ({
      ...w,
      cover_image: w.cover_image ?? null,
    }));
  }
  return res;
}

export async function resolveServerWard(
  ward: string,
  districtId?: string
): Promise<ResolveResult> {
  const searchParams = new URLSearchParams();
  searchParams.set("ward", ward);
  if (districtId) searchParams.set("district_id", districtId);

  try {
    const res = await fetchFromBackend<WardCard | ResolveChoices>(
      `locations/resolve?${searchParams.toString()}`
    );

    if (res.code === 200 && res.data) {
      return { type: "single", ward: res.data as WardCard };
    }
    if (res.code === 300 && res.data) {
      return {
        type: "choices",
        choices: (res.data as ResolveChoices).choices || [],
      };
    }
    return { type: "not_found" };
  } catch {
    return { type: "not_found" };
  }
}

export async function getServerMarketSummary(
  districtId?: string
): Promise<ApiEnvelope<MarketSummary>> {
  const searchParams = new URLSearchParams();
  if (districtId) searchParams.set("district_id", districtId);
  const q = searchParams.toString();
  return fetchFromBackend<MarketSummary>(
    `market/summary${q ? `?${q}` : ""}`,
    districtId ? [`market-summary-${districtId}`] : ["market-summary"]
  );
}

export async function getServerMarketDaily(
  districtId?: string,
  dateFrom: string = "2026-09-23",
  dateTo?: string
): Promise<ApiEnvelope<MarketDay[]>> {
  const searchParams = new URLSearchParams();
  if (districtId) searchParams.set("district_id", districtId);
  if (dateFrom) searchParams.set("date_from", dateFrom);
  if (dateTo) searchParams.set("date_to", dateTo);

  const q = searchParams.toString();
  return fetchFromBackend<MarketDay[]>(
    `market/daily${q ? `?${q}` : ""}`,
    districtId ? [`market-daily-${districtId}`] : ["market-daily"]
  );
}

export async function getServerListings(
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

  const q = searchParams.toString();
  const res = await fetchFromBackend<ListingCard[]>(`listings${q ? `?${q}` : ""}`, [
    "listings",
  ]);
  if (res.data) {
    res.data = res.data.map((l) => ({
      ...l,
      images: l.images ?? null,
    }));
  }
  return res;
}

export async function getServerListing(
  id: string
): Promise<ApiEnvelope<ListingDetail>> {
  const res = await fetchFromBackend<ListingDetail>(`listings/${id}`, [`listing-${id}`]);
  if (res.data) {
    res.data = {
      ...res.data,
      images: res.data.images ?? null,
    };
  }
  return res;
}

export async function getServerListingImages(
  id: string
): Promise<ApiEnvelope<ListingImage[]>> {
  try {
    return await fetchFromBackend<ListingImage[]>(`listings/${id}/images`, [
      `listing-images-${id}`,
    ]);
  } catch {
    return {
      success: true,
      code: 200,
      status: "OK",
      message: "No images",
      data: [],
      errors: null,
      meta: {} as any,
      links: null,
    };
  }
}

export async function getServerListingPriceHistory(
  id: string
): Promise<ApiEnvelope<PricePoint[]>> {
  return fetchFromBackend<PricePoint[]>(`listings/${id}/price-history`, [
    `listing-history-${id}`,
  ]);
}

export async function getServerModelCard(): Promise<ApiEnvelope<ModelCard>> {
  return fetchFromBackend<ModelCard>("price-estimates/model", ["price-model"]);
}
