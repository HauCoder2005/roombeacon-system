from enum import Enum


class CrawlStatus(str, Enum):
    """Trạng thái kết quả thu thập URL hoặc xử lý request."""

    SUCCESS = "success"
    BAD_REQUEST = "bad_request"
    UNAUTHORIZED = "unauthorized"
    ACCESS_DENIED = "access_denied"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    CLOUDFLARE_CHALLENGE = "cloudflare_challenge"
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    ROBOTS_DENIED = "robots_denied"
    UNSUPPORTED_SOURCE = "unsupported_source"
    UNSUPPORTED_TARGET = "unsupported_target"
    PARSE_ERROR = "parse_error"
    UNKNOWN = "unknown"
