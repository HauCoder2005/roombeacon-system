"""Extract JSON-LD or semantic detail fields from Guland posts."""
import re
from roombeacon_crawler.sources.common_html import SourceDetailParser

class GulandDetailParser(SourceDetailParser):
    PRICE_CLASSES=("post-price", "sdb-inf-price"); AREA_CLASSES=("post-area", "sdb-inf-area")
    DESCRIPTION_CLASSES=("post-description", "dtl-description"); ADDRESS_CLASSES=("dtl-stl__row", "post-address", "data-type-adr")
    SELLER_CLASSES=("profile-name", "author-name"); ID_PATTERN=re.compile(r"-(\d+)(?:$|[/?#])")
