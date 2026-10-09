export type ApiErrorDetail = {
  field: string | null;
  code: string;
  message: string;
};

export type DataSnapshot = {
  snapshot_id: string;
  loaded_at: string;
};

export type PaginationMeta = {
  page: number;
  per_page: number;
  total_items: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
};

export type CacheMeta = {
  etag: string;
  expires_at: string;
};

export type ApiMeta = {
  request_id: string;
  timestamp: string;
  api_version: "v1";
  method: string;
  path: string;
  duration_ms: number;
  resource: string | null;
  data_snapshot: DataSnapshot | null;
  cache: CacheMeta | null;
  pagination: PaginationMeta | null;
  sort: string[] | null;
  filters: Record<string, string> | null;
};

export type ApiEnvelope<T> = {
  success: boolean;
  code: number;
  status:
    | "OK"
    | "MULTIPLE_CHOICES"
    | "MOVED_PERMANENTLY"
    | "UNAUTHORIZED"
    | "NOT_FOUND"
    | "VALIDATION_ERROR"
    | "RATE_LIMITED"
    | "INTERNAL_ERROR"
    | "SERVICE_UNAVAILABLE"
    | string;
  message: string;
  data: T | null;
  errors: ApiErrorDetail[] | null;
  meta: ApiMeta;
  links: Record<string, string | null> | null;
};

export type Price = {
  currency: "VND";
  median: number | null;
  p25: number | null;
  p75: number | null;
  median_per_m2: number | null;
  median_area_m2: number | null;
};

export type CoverImage = {
  url: string;
  listing_id: string;
};

export type DistrictCard = {
  id: string;
  type: "district";
  name: string;
  stats: {
    listing_count: number;
    priced_listing_count: number;
    ward_count: number;
  };
  price: Price;
  cover_image: CoverImage | null;
  links: {
    self: string;
    wards: string;
  };
};

export type WardCard = {
  id: string;
  type: "ward";
  name: string;
  district: {
    id: string;
    name: string;
  };
  stats: {
    listing_count: number;
    priced_listing_count: number;
  };
  price: Price;
  cover_image: CoverImage | null;
  links: {
    district: string;
    district_wards: string;
  };
};

export type ListingImage = {
  position: number;
  url: string;
};

export type ResolveChoices = {
  choices: WardCard[];
};

export type ResolveResult =
  | { type: "single"; ward: WardCard }
  | { type: "choices"; choices: WardCard[] }
  | { type: "not_found" };

export type Ref = {
  id: string;
  name: string;
};

export type ListingValuation = {
  estimate: number;
  delta_pct: number;
  label: "BELOW_ESTIMATE" | "NEAR_ESTIMATE" | "ABOVE_ESTIMATE";
};

export type ListingCard = {
  id: string;
  type: "listing";
  title: string;
  source: string;
  source_url: string | null;
  price: {
    currency: "VND";
    amount: number;
    period: "month";
  } | null;
  area_m2: number | null;
  price_per_m2: number | null;
  location: {
    level: "WARD" | "DISTRICT" | "UNKNOWN";
    district: Ref | null;
    ward: Ref | null;
  };
  intent: "RENT" | "TRANSFER" | "SALE" | "UNKNOWN" | null;
  scope: string | null;
  first_observed_at: string | null;
  last_observed_at: string | null;
  active_days: number | null;
  quality: {
    price_suitability: string | null;
    duplicate_status: string | null;
  };
  valuation: ListingValuation | null;
  images: {
    count: number;
    cover: string | null;
    preview: string[];
  } | null;
  links: {
    self: string;
    price_history: string;
  };
};

export type MarketPosition = {
  scope: "ward" | "district";
  name: string;
  median: number | null;
  p25: number | null;
  p75: number | null;
  listing_count: number;
  position: "BELOW_P25" | "WITHIN_P25_P75" | "ABOVE_P75" | null;
};

export type ListingDetail = ListingCard & {
  market: MarketPosition | null;
};

export type PricePoint = {
  observed_at: string;
  price: number | null;
  area_m2: number | null;
  is_price_change: boolean;
  is_content_change: boolean;
};

export type PriceEstimateWarning =
  | "area_outside_typical_range"
  | "low_price_segment_less_accurate"
  | "high_price_segment_less_accurate"
  | "district_unknown_to_model"
  | "ward_unknown_to_model";

export type PriceEstimate = {
  estimate: number;
  range: {
    low: number;
    high: number;
    coverage: number;
  };
  inputs_used: {
    area_m2: number;
    district: string;
    ward: string | null;
    source_policy: string;
  };
  market: MarketPosition;
  warnings: PriceEstimateWarning[];
  disclaimer: string;
  model: {
    model_id: string;
    readiness: "experimental";
  };
};

export type ModelCard = {
  model_id: string;
  family: string;
  feature_set: string;
  target_transform: string;
  trained_until: string | null;
  test_metrics: {
    mae: number | null;
    median_ae: number | null;
    r2: number | null;
  };
  readiness: "experimental";
  reference_source: string;
  interval_coverage: number;
  typical_area_range: {
    low: number;
    high: number;
  };
  reliable_price_range: {
    low: number;
    high: number;
  };
};

export type MarketSummary = {
  scope: {
    type: "city" | "district";
    district: Ref | null;
  };
  listing_count: number;
  priced_listing_count: number;
  district_count: number;
  price: {
    currency: "VND";
    median: number | null;
    p25: number | null;
    p75: number | null;
  };
  data_from: string | null;
  data_until: string | null;
};

export type MarketDay = {
  date: string;
  listings_observed: number;
  new_listings: number;
  price_changes: number;
  median_price: number | null;
};

export type ListingQueryParams = {
  district_id?: string;
  ward_id?: string;
  q?: string;
  price_min?: number;
  price_max?: number;
  area_min?: number;
  area_max?: number;
  intent?: "RENT" | "TRANSFER" | "SALE" | "UNKNOWN" | "ANY";
  include_duplicates?: boolean;
  sort?:
    | "last_observed_at"
    | "-last_observed_at"
    | "price"
    | "-price"
    | "area"
    | "-area";
  page?: number;
  per_page?: number;
};
