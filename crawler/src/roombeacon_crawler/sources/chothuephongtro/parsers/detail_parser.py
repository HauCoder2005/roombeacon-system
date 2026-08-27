"""Extract semantic detail fields from ChoThuePhongTro posts."""
import re
from roombeacon_crawler.sources.common_html import SourceDetailParser

class ChothuephongtroDetailParser(SourceDetailParser):
    PRICE_CLASSES=("post-price",); AREA_CLASSES=("acreage",); DESCRIPTION_CLASSES=("post-content", "description")
    ADDRESS_CLASSES=("post-address", "location"); SELLER_CLASSES=("author-name", "user-name")
    ID_PATTERN=re.compile(r"-pr(\d+)\.html", re.I)
