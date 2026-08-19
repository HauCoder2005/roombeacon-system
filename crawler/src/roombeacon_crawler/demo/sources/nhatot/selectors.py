# Selectors and patterns for Nhatot (nhatot.com) rental listings

# Main listing area container (prevents matching sidebar / recommendations / footer)
MAIN_CONTAINER_CLASSES = (
    "ListAds_ListAds",
    "ListAds_wrapper",
    "ListAds",
    "list-view",
)

MAIN_CONTAINER_TESTIDS = (
    "list-ads",
    "ad-list",
)

# Individual listing card containers inside main container
CARD_CONTAINER_CLASSES = (
    "AdItem_adItemWrapper",
    "AdItem_wrapper",
    "AdItem_adItem",
)

CARD_CONTAINER_TESTIDS = (
    "ad-item",
)

# Field selectors strictly inside each card
TITLE_CLASSES = (
    "AdItem_title",
    "AdTitle",
    "ad-title",
    "title",
)

PRICE_CLASSES = (
    "AdItem_price",
    "AdPrice",
    "price",
)

AREA_CLASSES = (
    "AdItem_size",
    "AdItem_area",
    "size",
    "area",
    "square",
)

LOCATION_CLASSES = (
    "AdItem_location",
    "AdItem_address",
    "location",
    "address",
)
