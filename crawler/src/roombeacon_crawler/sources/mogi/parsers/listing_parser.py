"""Extract cards from Mogi prop-info containers."""
import re
from roombeacon_crawler.sources.common_html import SourceListingParser

class MogiListingParser(SourceListingParser):
    DETAIL_PATH_PREFIXES=("/quan-", "/huyen-", "/thanh-pho-")
    CARD_CLASSES=("prop-info",); LINK_CLASSES=("link-overlay",); PRICE_CLASSES=("price",)
    AREA_CLASSES=("prop-attr",); LOCATION_CLASSES=("prop-addr",); DATE_CLASSES=("prop-created",); IMAGE_CLASSES=("prop-img",)
    ID_PATTERN=re.compile(r"-id(\d+)(?:$|[/?#])", re.I)
