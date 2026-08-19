from enum import Enum


class FetchStrategy(str, Enum):
    """Chiến lược fetch được chỉ định cho từng nguồn dữ liệu."""

    HTTP = "http"
    BROWSER = "browser"
