from enum import Enum


class FetchAction(str, Enum):
    """Hành động tiếp theo sau khi phân loại response."""

    PARSE = "parse"
    COOLDOWN = "cooldown"
    RETRY_LATER = "retry_later"
    STOP = "stop"
