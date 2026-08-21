from enum import Enum


class SourceAccessProfile(str, Enum):
    """Hồ sơ truy cập nguồn (Source Access Profile).

    Phản ánh đặc tính truy cập hợp lệ và cơ chế khám phá phù hợp của từng website nguồn:
    - STANDARD_PAGINATION: Nguồn cho phép duyệt danh mục phân trang tiêu chuẩn qua query/path (vd: NhaTroVN, PhongTro123).
    - DISCOVERY_RESTRICTED: Nguồn giới hạn phân trang qua robots.txt / policy, yêu cầu khám phá qua Sitemap / Public Feeds (vd: NhaTot).
    - ACCESS_CHALLENGED: Nguồn trả về rào cản truy cập tự động (HTTP 403 / Cloudflare Challenge), yêu cầu dừng kiểm soát và xử lý tách biệt giữa Discovery và Content Access (vd: Muaban, BatDongSan).
    """

    STANDARD_PAGINATION = "STANDARD_PAGINATION"
    DISCOVERY_RESTRICTED = "DISCOVERY_RESTRICTED"
    ACCESS_CHALLENGED = "ACCESS_CHALLENGED"
