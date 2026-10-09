"use client";

import { useQuery, useMutation } from "@tanstack/react-query";
import {
  getClientDistricts,
  getClientDistrict,
  getClientDistrictWards,
  resolveClientWard,
  getClientListings,
  getClientListing,
  getClientListingPriceHistory,
  postClientPriceEstimate,
  getClientModelCard,
  getClientMarketSummary,
  getClientMarketDaily,
} from "./client";
import type { ListingQueryParams } from "../types/api";

export const STALE_TIME_MS = 5 * 60 * 1000; // 5 minutes

export function useDistricts(params?: {
  q?: string;
  sort?: string;
  page?: number;
  per_page?: number;
}) {
  return useQuery({
    queryKey: ["districts", params],
    queryFn: () => getClientDistricts(params),
    staleTime: STALE_TIME_MS,
  });
}

export function useDistrict(districtId: string | null | undefined) {
  return useQuery({
    queryKey: ["district", districtId],
    queryFn: () => (districtId ? getClientDistrict(districtId) : null),
    enabled: Boolean(districtId),
    staleTime: STALE_TIME_MS,
  });
}

export function useWards(
  districtId: string | null | undefined,
  params?: { q?: string; sort?: string; page?: number; per_page?: number }
) {
  return useQuery({
    queryKey: ["district_wards", districtId, params],
    queryFn: () =>
      districtId ? getClientDistrictWards(districtId, params) : null,
    enabled: Boolean(districtId),
    staleTime: STALE_TIME_MS,
  });
}

export function useDistrictWards(
  districtId: string | null | undefined,
  params?: { q?: string; sort?: string; page?: number; per_page?: number }
) {
  return useWards(districtId, params);
}

export function useResolveWard(
  ward: string,
  districtId?: string,
  enabled: boolean = true
) {
  return useQuery({
    queryKey: ["resolve_ward", ward, districtId],
    queryFn: () => resolveClientWard(ward, districtId),
    enabled: Boolean(ward.trim()) && enabled,
    staleTime: STALE_TIME_MS,
  });
}

export function useListings(params?: ListingQueryParams) {
  return useQuery({
    queryKey: ["listings", params],
    queryFn: () => getClientListings(params),
    staleTime: STALE_TIME_MS,
  });
}

export function useListing(id: string | null | undefined) {
  return useQuery({
    queryKey: ["listing", id],
    queryFn: () => (id ? getClientListing(id) : null),
    enabled: Boolean(id),
    staleTime: STALE_TIME_MS,
  });
}

export function usePriceHistory(id: string | null | undefined) {
  return useQuery({
    queryKey: ["listing_price_history", id],
    queryFn: () => (id ? getClientListingPriceHistory(id) : null),
    enabled: Boolean(id),
    staleTime: STALE_TIME_MS,
  });
}

export function useEstimate() {
  return useMutation({
    mutationFn: (body: {
      area_m2: number;
      district_id: string;
      ward_id?: string;
    }) => postClientPriceEstimate(body),
  });
}

export function useModelCard() {
  return useQuery({
    queryKey: ["price_model_card"],
    queryFn: () => getClientModelCard(),
    staleTime: STALE_TIME_MS,
  });
}

export function useMarketSummary(districtId?: string) {
  return useQuery({
    queryKey: ["market_summary", districtId],
    queryFn: () => getClientMarketSummary(districtId),
    staleTime: STALE_TIME_MS,
  });
}

export function useMarketDaily(
  districtId?: string,
  dateFrom: string = "2026-09-23",
  dateTo?: string
) {
  return useQuery({
    queryKey: ["market_daily", districtId, dateFrom, dateTo],
    queryFn: () => getClientMarketDaily(districtId, dateFrom, dateTo),
    staleTime: STALE_TIME_MS,
  });
}
