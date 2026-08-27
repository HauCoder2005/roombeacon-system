"""Extract cards from Guland c-sdb-card containers."""
import re
from roombeacon_crawler.sources.common_html import SourceListingParser

class GulandListingParser(SourceListingParser):
    DETAIL_PATH_PREFIXES=("/post/",)
    CARD_CLASSES=("c-sdb-card",); LINK_CLASSES=("sdb-image-wrap",)
    PRICE_CLASSES=("data-type-price", "sdb-inf-data"); AREA_CLASSES=("data-type-area",)
    LOCATION_CLASSES=("data-type-adr",); DATE_CLASSES=("sdb-card-time",); IMAGE_CLASSES=("c-sdb-card__img",)
    ID_PATTERN=re.compile(r"-(\d+)(?:$|[/?#])")
