"""Parse structured PhongTroToanQuoc detail content when access is eligible."""
from roombeacon_crawler.sources.common_html import SourceDetailParser

class PhongtrotoanquocDetailParser(SourceDetailParser):
    PRICE_CLASSES=("listing-price",); AREA_CLASSES=("listing-area",); DESCRIPTION_CLASSES=("listing-description",)
    ADDRESS_CLASSES=("listing-address",); SELLER_CLASSES=("seller-name",)
