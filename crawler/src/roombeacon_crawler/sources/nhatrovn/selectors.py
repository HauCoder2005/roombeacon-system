from dataclasses import dataclass


@dataclass(frozen=True)
class NhatroVNSelectors:
    """Tập hợp CSS Selectors bóc tách dữ liệu website NhatroVN (nhatrovn.vn)."""

    # --- Listing Selectors ---
    CARD_CONTAINER = "div.property-card"
    CARD_PARENT_LINK = "a[href*='/chi-tiet/']"
    CARD_IMAGE = "div.property-card-image img"
    CARD_ADDRESS = "div.rn-property-address"
    CARD_PRICE = "div.property-card-price"
    CARD_VACANT_BADGE = "div.rn-vacant-badge"
    CARD_TOTAL_ROOMS = "div.rn-property-total"
    CARD_BADGES = "div.property-card-badges div.property-card-badge"

    # --- Pagination Selectors ---
    PAGINATION_CONTAINER = "#paginationContainer"
    PAGINATION_ACTIVE_PAGE = ".pagination-btn.active"
    PAGINATION_PAGE_LINKS = ".pagination-btn"
    PAGINATION_NEXT_ARROW = ".pagination-btn.pagination-arrow:not(.disabled)"
    PAGINATION_INFO = "div.text-center small.text-muted"

    # --- Detail Selectors ---
    DETAIL_ROOM_CODE = "h1.room-code"
    DETAIL_BREADCRUMB_ACTIVE = "ol.breadcrumb li.breadcrumb-item.active"
    DETAIL_ADDRESS = "div.rs-card-address"
    DETAIL_PRICE_VALUE = "div.rs-card-price .rs-card-price__value"
    DETAIL_PRICE_CONTAINER = "div.rs-card-price"
    DETAIL_INFO_BADGES = "span.rs-info-badge"
    DETAIL_CAROUSEL_IMAGES = "div.carousel-slide img[src], div.carousel-thumb img[src]"
    DETAIL_AMENITIES_ACTIVE = "div.rs-amenity-chip:not(.rs-amenity-chip--inactive) .rs-amenity-chip__label"
    DETAIL_COST_ITEMS = "div.rs-fee-item"
    DETAIL_SUMMARY_LEAD = "p.rs-summary__lead"
    DETAIL_SUMMARY_LIST = "ul.rs-summary__list"
    DETAIL_SPECS_GRID = "div.rs-detail-grid .rs-detail-item"
