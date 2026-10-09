import type { ListingCard, ListingValuation } from "@/lib/types/api";

/**
 * Shadow validation (notebook 06) shows the experimental model is unreliable for
 * rents below ~2.5M (dorm beds, shared rooms) and above ~6M, so the UI only shows
 * a valuation label inside that band and never for extreme gaps.
 */
export const RELIABLE_LISTING_PRICE = { low: 2_500_000, high: 6_000_000 } as const;
const MAX_ABS_DELTA_PCT = 50;

export function trustworthyValuation(listing: Pick<ListingCard, "valuation" | "price">): ListingValuation | null {
  const valuation = listing.valuation;
  const asking = listing.price?.amount;
  if (!valuation || !asking) return null;
  if (asking < RELIABLE_LISTING_PRICE.low || asking > RELIABLE_LISTING_PRICE.high) return null;
  if (Math.abs(valuation.delta_pct) > MAX_ABS_DELTA_PCT) return null;
  return valuation;
}
