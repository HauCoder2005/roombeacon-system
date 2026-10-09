import "server-only";
import { NextRequest, NextResponse } from "next/server";
import { checkRateLimit, rateLimitedBody, rateLimitedResponseInit } from "@/lib/server/rateLimit";

const ALLOWED =
  /^(locations\/(districts(\/[0-9a-f]{16}(\/wards)?)?|resolve)|listings(\/[0-9]{1,19}(\/(price-history|images))?)?|market\/(summary|daily)|price-estimates\/model)$/;
const IMAGE = /^listings\/[0-9]{1,19}\/images\/[0-9]{1,4}$/;
const PASS_HEADERS = [
  "Retry-After",
  "ETag",
  "X-Request-ID",
  "X-RateLimit-Limit",
  "X-RateLimit-Remaining",
];

// Ảnh: chuyển nguyên byte; chỉ chấp nhận image/*; cache trình duyệt 1 ngày.
const IMAGE_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
]);

async function proxyImage(path: string) {
  const upstream = await fetch(
    `${process.env.ROOMBEACON_API_URL}/api/v1/${path}`,
    {
      headers: { "X-API-Key": process.env.ROOMBEACON_API_KEY ?? "" },
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    }
  );
  const type = (upstream.headers.get("content-type") ?? "").split(";")[0];
  if (!upstream.ok || !IMAGE_TYPES.has(type)) {
    return new NextResponse(null, {
      status: upstream.ok ? 404 : upstream.status,
    });
  }
  return new NextResponse(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": type,
      "Cache-Control": "public, max-age=86400",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const path = (await params).path.join("/");
  const decision = checkRateLimit(IMAGE.test(path) ? "image" : "json", req.headers);
  if (!decision.allowed) return new NextResponse(rateLimitedBody(decision), rateLimitedResponseInit(decision));
  if (IMAGE.test(path)) return proxyImage(path);
  if (!ALLOWED.test(path)) {
    return NextResponse.json(
      { success: false, code: 404, status: "NOT_FOUND" },
      { status: 404 }
    );
  }
  const headers: Record<string, string> = {
    "X-API-Key": process.env.ROOMBEACON_API_KEY ?? "",
  };
  const ifNoneMatch = req.headers.get("if-none-match");
  if (ifNoneMatch) headers["If-None-Match"] = ifNoneMatch;

  const upstream = await fetch(
    `${process.env.ROOMBEACON_API_URL}/api/v1/${path}${req.nextUrl.search}`,
    {
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    }
  );

  const out = new Headers({ "Content-Type": "application/json; charset=utf-8" });
  for (const name of PASS_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  return new NextResponse(
    upstream.status === 304 ? null : await upstream.text(),
    {
      status: upstream.status,
      headers: out,
    }
  );
}

// Chỉ một endpoint ghi: định giá. Thân request tối đa 2 KB, chuyển nguyên JSON.
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const decision = checkRateLimit("json", req.headers);
  if (!decision.allowed) return new NextResponse(rateLimitedBody(decision), rateLimitedResponseInit(decision));
  if ((await params).path.join("/") !== "price-estimates") {
    return NextResponse.json(
      { success: false, code: 404, status: "NOT_FOUND" },
      { status: 404 }
    );
  }
  const body = await req.text();
  if (body.length > 2048) {
    return NextResponse.json({ success: false, code: 413 }, { status: 413 });
  }

  const upstream = await fetch(
    `${process.env.ROOMBEACON_API_URL}/api/v1/price-estimates`,
    {
      method: "POST",
      headers: {
        "X-API-Key": process.env.ROOMBEACON_API_KEY ?? "",
        "Content-Type": "application/json",
      },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    }
  );

  const out = new Headers({ "Content-Type": "application/json; charset=utf-8" });
  for (const name of ["Retry-After", "X-Request-ID"]) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  return new NextResponse(await upstream.text(), {
    status: upstream.status,
    headers: out,
  });
}
