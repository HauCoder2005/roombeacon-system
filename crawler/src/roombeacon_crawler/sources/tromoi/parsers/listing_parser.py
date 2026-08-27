"""Extract cards from TroMoi hostel-item containers."""
from roombeacon_crawler.sources.common_html import SourceListingParser

class TromoiListingParser(SourceListingParser):
    DETAIL_PATH_PREFIXES=("/phong-tro/", "/ky-tuc-xa/", "/nha-nguyen-can/", "/can-ho/")
    CARD_CLASSES=("hostel-item",); LINK_CLASSES=("hostel-item__link", "hostel-item__img--link")
    PRICE_CLASSES=("hostel-item__price",); AREA_CLASSES=("hostel-item__area",)
    LOCATION_CLASSES=("hostel-item__address", "hostel-item__location"); DATE_CLASSES=("hostel-item__date",)
    IMAGE_CLASSES=("hostel-item__img",)
