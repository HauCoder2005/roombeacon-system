"""Extract explicit map evidence without network requests or inferred coordinates."""

import base64
import binascii
import re
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from roombeacon_crawler.models.map_location import MapLocation

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_PAIR = re.compile(rf"^\s*({_NUMBER})\s*,\s*({_NUMBER})\s*$")


class MapLocationExtractor:
    @staticmethod
    def extract_map_from_html(html: str) -> MapLocation | None:
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        candidates = []
        for node in soup.find_all(["iframe", "a"]):
            for attr in ("data-src", "data-lazy-src", "src", "href"):
                if node.get(attr):
                    candidates.append(node[attr])
        # Some sources create the iframe from a JavaScript variable.
        candidates.extend(re.findall(
            r"(?:var|let|const)\s+urlMapIframe\s*=\s*['\"]([^'\"]+)['\"]", html
        ))
        best = None
        for url in dict.fromkeys(candidates):
            location = MapLocationExtractor.extract_from_url(url)
            if location is None:
                continue
            score = lambda item: (item.latitude is not None, bool(item.query_raw))
            if best is None or score(location) > score(best):
                best = location
        return best

    @staticmethod
    def extract_from_url(url: str) -> MapLocation | None:
        if not url:
            return None
        raw = url
        url = unescape(url).replace(r"\/", "/")
        try:
            parsed = urlparse("https:" + url if url.startswith("//") else url)
            host = (parsed.hostname or "").lower()
        except ValueError:
            return None
        if parsed.scheme not in {"http", "https"}:
            return None
        if not (host in {"maps.google.com", "maps.google.com.vn"} or (
            host in {"google.com", "www.google.com", "google.com.vn", "www.google.com.vn"}
            and (parsed.path == "/maps" or parsed.path.startswith("/maps/"))
        )):
            return None
        qs = parse_qs(parsed.query)
        query = None
        latitude = longitude = None

        def set_pair(first: str, second: str) -> bool:
            nonlocal latitude, longitude
            lat, lon = float(first), float(second)
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                latitude, longitude = lat, lon
                return True
            return False

        for key in ("q", "query", "destination"):
            value = qs.get(key, [""])[0].strip()
            if not value:
                continue
            match = _PAIR.fullmatch(value)
            if match and set_pair(*match.groups()):
                break
            query = value

        # Decode once: parse_qs has already decoded the query string.
        payload = qs.get("pb", [""])[0] or unquote(parsed.path)
        if latitude is None:
            for pattern, reverse in (
                (rf"!3d({_NUMBER})!4d({_NUMBER})", False),
                (rf"!2d({_NUMBER})!3d({_NUMBER})", True),
                (rf"/@({_NUMBER}),({_NUMBER})", False),
            ):
                match = re.search(pattern, payload)
                if match and set_pair(*(match.groups()[::-1] if reverse else match.groups())):
                    break
        if latitude is None:
            for key in ("ll", "center"):
                match = _PAIR.fullmatch(qs.get(key, [""])[0])
                if match and set_pair(*match.groups()):
                    break
        if not query:
            encoded = re.search(r"!2z([a-zA-Z0-9_\-=]+)", payload)
            if encoded:
                value = encoded.group(1)
                try:
                    query = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode("utf-8").strip() or None
                except (ValueError, UnicodeDecodeError, binascii.Error):
                    pass
            if not query:
                label = re.search(r"!2s([^!]+)", payload)
                if label and label.group(1) not in {"vi", "en", "vi-VN", "en-US"}:
                    query = label.group(1).strip() or None
        if latitude is None and not query:
            return None
        return MapLocation(
            provider="google_maps_embed", map_url_raw=raw,
            latitude=latitude, longitude=longitude, query_raw=query,
        )
