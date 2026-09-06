import re
from urllib.parse import urlparse, parse_qs
from dataclasses import dataclass
from crawler.src.roombeacon_crawler.sources.common_html import HtmlNode

@dataclass
class LocationCandidate:
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    source_url: str | None = None

def extract_google_maps_info(
    root: HtmlNode | None, html: str | None = None
) -> LocationCandidate:
    cand = LocationCandidate()
    if not root:
        return cand

    # 1. iframe parsing
    for iframe in root.find_all(tag="iframe"):
        src = iframe.attrs.get("src") or iframe.attrs.get("data-src") or ""
        src = src.strip()
        if "google.com/maps" in src or "maps.google.com" in src:
            parsed = urlparse(src)
            qs = parse_qs(parsed.query)
            
            # extract coordinates from q=lat,lng
            if "q" in qs:
                q_val = qs["q"][0]
                coords_match = re.search(r"(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)", q_val)
                if coords_match:
                    cand.latitude = float(coords_match.group(1))
                    cand.longitude = float(coords_match.group(2))
                else:
                    cand.address = q_val.replace("+", " ").strip()
            
            # center/ll parameters
            if not cand.latitude and not cand.longitude:
                for param in ("ll", "center", "sll"):
                    if param in qs:
                        coords_match = re.search(r"(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)", qs[param][0])
                        if coords_match:
                            cand.latitude = float(coords_match.group(1))
                            cand.longitude = float(coords_match.group(2))
                            break

            if cand.latitude or cand.longitude or cand.address:
                return cand

    # 2. data attributes on elements
    for el in root.find_all():
        lat = el.attrs.get("data-lat") or el.attrs.get("data-latitude")
        lng = el.attrs.get("data-lng") or el.attrs.get("data-longitude")
        addr = el.attrs.get("data-address")
        if lat and lng:
            try:
                cand.latitude = float(lat)
                cand.longitude = float(lng)
            except ValueError:
                pass
        if addr:
            cand.address = addr
        if cand.latitude or cand.longitude or cand.address:
            return cand

    # 4. Base64 encoded map configuration (Modern SPA/React/Vue apps)
    import base64
    import json
    for el in root.find_all():
        for attr in ("data-map", "data-config", "data-location"):
            val = el.attrs.get(attr)
            if not val:
                continue
            # Try to decode if it looks like base64
            if len(val) > 10 and not val.startswith("{") and not val.startswith("["):
                try:
                    decoded = base64.b64decode(val).decode("utf-8")
                    data = json.loads(decoded)
                    if isinstance(data, dict):
                        # Handle various common coordinate keys
                        lat = data.get("lat") or data.get("latitude")
                        lng = data.get("lng") or data.get("longitude") or data.get("lon")
                        if lat is not None and lng is not None:
                            cand.latitude = float(lat)
                            cand.longitude = float(lng)
                            return cand
                except Exception:
                    pass

    # 3. JSON-LD geo
    for script in root.find_all(tag="script"):
        if script.attrs.get("type") == "application/ld+json":
            try:
                import json
                data = json.loads(script.text())
                if isinstance(data, dict):
                    geo = data.get("geo")
                    if isinstance(geo, dict):
                        lat = geo.get("latitude")
                        lng = geo.get("longitude")
                        if lat is not None and lng is not None:
                            cand.latitude = float(lat)
                            cand.longitude = float(lng)
                            return cand
            except Exception:
                pass

    return cand
