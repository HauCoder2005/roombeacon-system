"""Contact-number detection and masking (Vietnamese phone formats).

Listing titles and URLs scraped from sources sometimes embed phone numbers.
Nothing that leaves the API may carry them.
"""

from __future__ import annotations

import re


CONTACT_NUMBER = re.compile(r"(?<!\d)(?:\+?84|0)(?:[\s.-]?\d){8,10}(?!\d)")
MASK = "***"


def contains_contact_number(text: str | None) -> bool:
    return bool(text) and bool(CONTACT_NUMBER.search(text))


def mask_contact_numbers(text: str | None) -> str | None:
    return None if text is None else CONTACT_NUMBER.sub(MASK, text)
