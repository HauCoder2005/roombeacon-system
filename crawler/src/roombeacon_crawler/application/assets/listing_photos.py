"""Pick a listing's own photos out of every <img> URL its detail page carried.

Detail parsers record all page images: logos, icons, avatars, tracking pixels
and the thumbnails of related listings. Downloading those wastes the asset
budget and shows the wrong room on a card, so the reconciler keeps only URLs
that match the source's own gallery. Sources without a known gallery pattern
fall back to dropping obvious page chrome. Positions are kept as recorded.

The Bronze loader puts the search-card thumbnail of the listing first, so the
first image of a version is the listing's own cover unless it is page chrome.
"""

from __future__ import annotations

import re
from typing import Callable, Iterable

ImageRow = tuple[int, str]

_CHROME = re.compile(
    r"(\.svg(\?|$)|logo|favicon|icon|avatar|default[-_]user|badge|dmca|empty_state|"
    r"facebook\.com/tr|googleplay|applestore|app_store|google_play|bocongthuong|bo-cong-thuong)",
    re.IGNORECASE,
)
_TROMOI_HOSTEL = re.compile(r"^https://tromoi\.com/storage/uploads/hosts/\d+/hostels/(\d+)/")
_TROMOI_UPLOAD = re.compile(r"^https://tromoi\.com/storage/(legacy_)?uploads/")
_TROMOI_ICONS = "tromoi.com/images/icons/"


def is_page_chrome(url: str) -> bool:
    """Logos, icons, avatars, tracking pixels, inline data and relative site assets."""
    return not url.startswith(("http://", "https://")) or _CHROME.search(url) is not None


def _pattern(regex: str) -> Callable[[str, str], bool]:
    compiled = re.compile(regex)
    return lambda url, _post_id: compiled.match(url) is not None


_GALLERY: dict[str, Callable[[str, str], bool]] = {
    # static123 serves the detail gallery at 900x600; 450x300 thumbs are related-listing cards.
    "phongtro123": _pattern(r"^https://pt123\.cdn\.static123\.com/images/thumbs/900x600/"),
    "chothuephongtro": _pattern(r"^https://ctpt\.cdn\.static123\.com/images/thumbs/900x600/"),
    "cafeland": _pattern(r"^https://static2\.cafeland\.vn/static\d+/sgd/"),
    "mogi": _pattern(r"^https://cloud\.mogi\.vn/images/"),
    "nhatot": _pattern(r"^https://cdn\.chotot\.com/[^/]+/preset:view/"),
    "chothuenha": _pattern(r"^https://giga-images\.s3\.ap-southeast-1\.amazonaws\.com/"),
    "nhatrovn": lambda url, post_id: url.startswith("https://api.nhatrovn.vn/api/common/img/")
    and f"/images-room/{post_id}/" in url,
    "tromoi": lambda url, _post_id: _TROMOI_UPLOAD.match(url) is not None,
}


def select_listing_photos(source: str, platform_post_id: str, images: Iterable[ImageRow]) -> list[ImageRow]:
    """The listing's own photos in position order, each URL once."""
    ordered = sorted(images, key=lambda row: row[0])
    if not ordered:
        return []
    gallery = _GALLERY.get(source)
    if gallery is None:
        kept = [row for row in ordered if not is_page_chrome(row[1])]
    else:
        kept = [row for row in ordered if gallery(row[1], platform_post_id)]
    if source == "tromoi" and kept:
        kept = _tromoi_own(ordered, kept)
    cover = ordered[0]
    if not is_page_chrome(cover[1]) and cover not in kept:
        kept.insert(0, cover)
    seen: set[str] = set()
    unique = []
    for position, url in kept:
        if url not in seen:
            seen.add(url)
            unique.append((position, url))
    return unique


def _tromoi_own(ordered: list[ImageRow], kept: list[ImageRow]) -> list[ImageRow]:
    """The gallery ends where the amenity icons start; uploads after them are related rooms."""
    icons = [position for position, url in ordered if _TROMOI_ICONS in url]
    if icons:
        return [row for row in kept if row[0] < icons[0]]
    # No icon block: keep only the hostel of the first hostel upload.
    hostels = [m.group(1) for _p, url in kept for m in [_TROMOI_HOSTEL.match(url)] if m]
    if not hostels:
        return kept
    return [row for row in kept if (m := _TROMOI_HOSTEL.match(row[1])) is None or m.group(1) == hostels[0]]


def select_post_photos(
    source: str, platform_post_id: str, versions: Iterable[Iterable[ImageRow]]
) -> list[ImageRow]:
    """Own photos across every observed version: a card-only version must not hide a detail gallery."""
    best: dict[str, int] = {}
    for images in versions:
        for position, url in select_listing_photos(source, platform_post_id, images):
            if url not in best or position < best[url]:
                best[url] = position
    return sorted(((position, url) for url, position in best.items()), key=lambda row: (row[0], row[1]))
