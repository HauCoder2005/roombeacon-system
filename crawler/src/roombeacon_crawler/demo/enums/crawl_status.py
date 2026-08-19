from enum import Enum


class CrawlStatus(str, Enum):
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
    UNKNOWN = "unknown"