"""Extract listing cards from the audited ChoThueNha card DOM."""
import re
from roombeacon_crawler.sources.common_html import SourceListingParser

class ChothuenhaListingParser(SourceListingParser):
    CARD_CLASSES = ("dv-bds",)
    PRICE_CLASSES = ("price",)
    AREA_CLASSES = ("area", "dientich")
    LOCATION_CLASSES = ("location", "address")
    DATE_CLASSES = ("date", "time")
    IMAGE_CLASSES = ("home-thumb",)
    ID_PATTERN = re.compile(r"-(\d+)(?:$|[/?#])")
