"""Extract structured and scoped detail fields from Mogi properties."""
import re
from roombeacon_crawler.sources.common_html import SourceDetailParser

class MogiDetailParser(SourceDetailParser):
    MAP_CLASSES = ("map-content",)

    PRICE_CLASSES=("price", "property-price"); AREA_CLASSES=("property-area", "prop-attr")
    DESCRIPTION_CLASSES=("info-content-body", "property-description", "info-content"); ADDRESS_CLASSES=("property-address", "address")
    SELLER_CLASSES=("agent-name", "author-name"); ID_PATTERN=re.compile(r"-id(\d+)(?:$|[/?#])", re.I)
