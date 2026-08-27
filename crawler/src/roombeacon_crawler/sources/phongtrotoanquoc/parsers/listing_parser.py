"""Parse server-rendered PhongTroToanQuoc cards when the site exposes them."""
from roombeacon_crawler.sources.common_html import SourceListingParser

class PhongtrotoanquocListingParser(SourceListingParser):
    CARD_CLASSES=("listing-card", "property-card"); LINK_CLASSES=("listing-link",)
    PRICE_CLASSES=("listing-price",); AREA_CLASSES=("listing-area",); LOCATION_CLASSES=("listing-address",)
    DATE_CLASSES=("listing-date",); IMAGE_CLASSES=("listing-image",)
