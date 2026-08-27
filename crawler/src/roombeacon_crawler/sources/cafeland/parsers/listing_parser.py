"""Extract cards from CafeLand row-item containers."""
import re
from roombeacon_crawler.sources.common_html import SourceListingParser

class CafelandListingParser(SourceListingParser):
    """Apply this source's listing-card HTML contract without semantic cleaning."""
    CARD_CLASSES=("row-item",); PRICE_CLASSES=("price", "reals-price"); AREA_CLASSES=("reals-area", "acreage")
    LOCATION_CLASSES=("reals-address", "location"); DATE_CLASSES=("reals-date", "date"); IMAGE_CLASSES=("image-frame",)
    ID_PATTERN=re.compile(r"-(\d+)\.html", re.I)
