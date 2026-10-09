import "server-only";

/**
 * In-process sliding-window limits for the /api/rb BFF.
 *
 * Every browser shares ONE backend API key, so without this a single client could
 * spend the whole backend budget. Two layers:
 *  - per client (keyed by the forwarded client address), and
 *  - a global ceiling, so spoofed X-Forwarded-For values still cannot exceed the
 *    backend budget. Behind a reverse proxy that overwrites X-Forwarded-For the
 *    per-client layer is exact; without one it is best effort.
 * State lives in memory: run one Next.js instance (or move this to Redis).
 */

type Decision = { allowed: boolean; limit: number; remaining: number; retryAfter: number };

const WINDOW_MS = 60_000;
const MAX_CLIENTS = 10_000;

class SlidingWindow {
  private hits = new Map<string, number[]>();

  constructor(readonly limit: number) {}

  hit(key: string, now: number): Decision {
    const kept = (this.hits.get(key) ?? []).filter((t) => now - t < WINDOW_MS);
    const allowed = kept.length < this.limit;
    if (allowed) kept.push(now);
    this.hits.delete(key);
    this.hits.set(key, kept);
    if (this.hits.size > MAX_CLIENTS) {
      const oldest = this.hits.keys().next().value;
      if (oldest !== undefined) this.hits.delete(oldest);
    }
    const retryAfter = allowed ? 0 : Math.max(1, Math.ceil((WINDOW_MS - (now - kept[0])) / 1000));
    return { allowed, limit: this.limit, remaining: Math.max(0, this.limit - kept.length), retryAfter };
  }
}

function envLimit(name: string, fallback: number): number {
  const value = Number.parseInt(process.env[name] ?? "", 10);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

const limiters = {
  json: { client: new SlidingWindow(envLimit("BFF_RATE_LIMIT_PER_MINUTE", 120)), global: new SlidingWindow(envLimit("BFF_GLOBAL_RATE_LIMIT_PER_MINUTE", 550)) },
  image: { client: new SlidingWindow(envLimit("BFF_IMAGE_RATE_LIMIT_PER_MINUTE", 600)), global: new SlidingWindow(envLimit("BFF_GLOBAL_IMAGE_RATE_LIMIT_PER_MINUTE", 5000)) },
};

/** Rightmost X-Forwarded-For entry: the hop closest to this server. */
export function clientKey(headers: Headers): string {
  const forwarded = headers.get("x-forwarded-for") ?? "";
  const hop = forwarded.split(",").map((part) => part.trim()).filter(Boolean).pop();
  return (hop ?? "unknown").slice(0, 64);
}

export function checkRateLimit(kind: "json" | "image", headers: Headers, now = Date.now()): Decision {
  const { client, global } = limiters[kind];
  const perClient = client.hit(clientKey(headers), now);
  if (!perClient.allowed) return perClient;
  const overall = global.hit("global", now);
  return overall.allowed ? perClient : overall;
}

export function rateLimitedResponseInit(decision: Decision): ResponseInit {
  return {
    status: 429,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Retry-After": String(decision.retryAfter),
      "X-RateLimit-Limit": String(decision.limit),
      "X-RateLimit-Remaining": "0",
      "Cache-Control": "no-store",
    },
  };
}

export function rateLimitedBody(decision: Decision): string {
  return JSON.stringify({
    success: false,
    code: 429,
    status: "RATE_LIMITED",
    message: `Too many requests; retry after ${decision.retryAfter} seconds`,
    data: null,
    errors: [{ field: null, code: "rate_limited", message: `limit is ${decision.limit} requests per minute` }],
    meta: null,
    links: null,
  });
}
