import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class NhatotMetadataParser:
    """Parser trích xuất metadata nhúng (OpenGraph, Schema.org JSON-LD, meta tags) từ HTML."""

    @staticmethod
    def parse_meta_tags(html: str) -> dict[str, str]:
        """Trích xuất các thẻ meta name/property từ thẻ head của trang HTML."""
        meta_dict: dict[str, str] = {}
        if not html:
            return meta_dict

        matches = re.findall(
            r'<meta\s+(?:[^>]*?\s+)?(?:name|property)=["\']([^"\']+)["\']\s+content=["\']([^"\']*)["\']',
            html,
            re.IGNORECASE,
        )
        for name, content in matches:
            meta_dict[name.lower()] = content

        return meta_dict

    @staticmethod
    def parse_json_ld(html: str) -> list[dict[str, Any]]:
        """Trích xuất các khối dữ liệu cấu trúc Schema.org dạng application/ld+json."""
        if not html:
            return []

        scripts = re.findall(
            r'<script\s+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        results: list[dict[str, Any]] = []
        for s in scripts:
            try:
                data = json.loads(s.strip())
                if isinstance(data, dict):
                    results.append(data)
                elif isinstance(data, list):
                    results.extend([item for item in data if isinstance(item, dict)])
            except Exception:
                continue

        return results
