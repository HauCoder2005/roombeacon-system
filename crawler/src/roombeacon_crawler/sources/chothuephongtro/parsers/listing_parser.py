"""Extract cards from ChoThuePhongTro post-item containers."""
import re
from roombeacon_crawler.sources.common_html import SourceListingParser

class ChothuephongtroListingParser(SourceListingParser):
    CARD_CLASSES=("post-item",); PRICE_CLASSES=("post-price",); AREA_CLASSES=("acreage",)
    LOCATION_CLASSES=("location",); DATE_CLASSES=("date",); IMAGE_CLASSES=("thumb",)
    ID_PATTERN=re.compile(r"-pr(\d+)\.html", re.I)
