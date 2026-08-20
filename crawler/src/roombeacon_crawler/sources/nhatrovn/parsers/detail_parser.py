import logging
import re
from urllib.parse import urljoin

from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw
from roombeacon_crawler.sources.nhatrovn.dom import DOMTreeBuilder

logger = logging.getLogger(__name__)


class NhatroVNDetailParser:
    """Parser bóc tách toàn bộ thông tin chi tiết một phòng trọ từ HTML trang detail của NhatroVN."""

    def __init__(self, source_name: str = "nhatrovn") -> None:
        self.source_name = source_name

    def parse(
        self,
        html: str,
        detail_url: str,
        listing_id: str | None = None,
    ) -> ListingDetailRaw:
        """Bóc tách dữ liệu chi tiết của phòng trọ từ HTML."""
        if not html:
            return ListingDetailRaw(
                source=self.source_name,
                listing_id=listing_id,
                detail_url=detail_url,
                title_raw=None,
                price_raw=None,
                area_raw=None,
                address_raw=None,
                location_raw=None,
                description_raw=None,
                posted_at_raw=None,
            )

        root = DOMTreeBuilder.parse(html)

        # 1. Listing ID
        if not listing_id:
            match = re.search(r"/chi-tiet/([a-zA-Z0-9]+)/?", detail_url)
            listing_id = match.group(1) if match else None

        # 2. Tiêu đề / Tên phòng
        title_elem = (
            root.find(tag="h1", class_contains="room-code")
            or root.find(tag="li", class_contains="active")
        )
        title_raw = title_elem.get_text() if title_elem else None
        if not title_raw:
            page_title = root.find(tag="title")
            title_raw = page_title.get_text() if page_title else None

        # 3. Địa chỉ
        address_elem = root.find(class_contains="rs-card-address")
        address_raw = None
        if address_elem:
            address_raw = address_elem.get_text()
            address_raw = re.sub(r"^location_on\s*", "", address_raw).strip()

        # 4. Giá
        price_elem = (
            root.find(class_contains="rs-card-price__value")
            or root.find(class_contains="rs-card-price")
        )
        price_raw = price_elem.get_text() if price_elem else None

        # 5. Diện tích & Vị trí / Tầng từ Meta Chips / Info Badges (Khớp chính xác class cha)
        area_raw = None
        position_raw = None
        badges = root.find_all(
            predicate=lambda n: "rs-info-badge" in n.get("class").split()
        )
        for badge in badges:
            text = badge.get_text()
            if "Diện tích" in text or "m2" in text or "m²" in text:
                val_elem = badge.find(class_contains="rs-info-badge__val")
                area_raw = val_elem.get_text() if val_elem else text
            elif "Vị trí" in text or "Tầng" in text:
                val_elem = badge.find(class_contains="rs-info-badge__val")
                position_raw = val_elem.get_text() if val_elem else text

        # 6. Danh sách hình ảnh (Deduplicated)
        image_urls_raw: list[str] = []
        img_elements = root.find_all(
            tag="img",
            predicate=lambda n: bool(
                n.find_parent(class_contains="carousel-slide")
                or n.find_parent(class_contains="carousel-thumb")
                or n.find_parent(class_contains="carousel-main")
            ),
        )
        for img in img_elements:
            src = img.get("src") or img.get("data-src")
            if src and not src.startswith("data:"):
                full_img_url = urljoin(detail_url, src.strip())
                if full_img_url not in image_urls_raw:
                    image_urls_raw.append(full_img_url)

        # 7. Tiện ích (Amenities - chỉ lấy các mục active)
        amenities_raw: list[str] = []
        amenity_elements = root.find_all(
            predicate=lambda n: (
                "rs-amenity-chip" in n.get("class").split()
                and "rs-amenity-chip--inactive" not in n.get("class")
            ),
        )
        for a_elem in amenity_elements:
            label = a_elem.find(class_contains="rs-amenity-chip__label") or a_elem
            a_text = label.get_text()
            if a_text and a_text not in amenities_raw:
                amenities_raw.append(a_text)

        # 8. Chi phí / Biểu phí chi tiết (Fee items)
        electricity_cost_raw = None
        water_cost_raw = None
        management_fee_raw = None
        parking_fee_raw = None
        internet_fee_raw = None

        cost_items = root.find_all(
            predicate=lambda n: "rs-fee-item" in n.get("class").split()
        )
        for item in cost_items:
            cost_key = item.get("data-cost-key", "").lower()
            text = item.get_text()
            if cost_key == "electricity" or "điện" in text.lower():
                electricity_cost_raw = text
            elif cost_key == "water" or "nước" in text.lower():
                water_cost_raw = text
            elif cost_key in ("management", "service") or "quản lý" in text.lower() or "dịch vụ" in text.lower():
                management_fee_raw = text
            elif cost_key in ("parking", "vehicle") or "xe" in text.lower():
                parking_fee_raw = text
            elif cost_key in ("wifi", "internet") or "wifi" in text.lower() or "mạng" in text.lower():
                internet_fee_raw = text

        # 9. Mô tả chi tiết (Description - bảo toàn câu từ nguyên bản)
        desc_parts: list[str] = []
        summary_lead = root.find(class_contains="rs-summary__lead")
        if summary_lead:
            desc_parts.append(summary_lead.get_text())

        summary_list = root.find(class_contains="rs-summary__list")
        if summary_list:
            for li in summary_list.find_all(tag="li"):
                li_text = li.get_text()
                if li_text:
                    desc_parts.append(li_text)

        desc_container = root.find(class_contains="rs-description") or root.find(class_contains="room-description")
        if desc_container:
            for p in desc_container.find_all(tag="p"):
                p_text = p.get_text()
                if p_text and p_text not in desc_parts:
                    desc_parts.append(p_text)

        description_raw = "\n".join(desc_parts).strip() if desc_parts else None

        # 10. Số lượng phòng trống / Tổng số phòng nếu có
        vacant_badge = root.find(class_contains="rn-vacant-badge")
        available_rooms_raw = vacant_badge.get_text() if vacant_badge else None

        total_badge = root.find(class_contains="rn-property-total")
        total_rooms_raw = total_badge.get_text() if total_badge else None

        return ListingDetailRaw(
            source=self.source_name,
            listing_id=listing_id,
            detail_url=detail_url,
            title_raw=title_raw,
            price_raw=price_raw,
            area_raw=area_raw,
            address_raw=address_raw,
            location_raw=address_raw,
            description_raw=description_raw,
            posted_at_raw=None,
            updated_at_raw=None,
            property_type_raw=None,
            room_type_raw=None,
            position_raw=position_raw,
            furnishing_raw=None,
            deposit_raw=None,
            electricity_cost_raw=electricity_cost_raw,
            water_cost_raw=water_cost_raw,
            management_fee_raw=management_fee_raw,
            parking_fee_raw=parking_fee_raw,
            internet_fee_raw=internet_fee_raw,
            available_rooms_raw=available_rooms_raw,
            total_rooms_raw=total_rooms_raw,
            verification_raw=None,
            seller_name_raw=None,
            seller_type_raw=None,
            image_urls_raw=image_urls_raw,
            amenities_raw=amenities_raw,
        )
