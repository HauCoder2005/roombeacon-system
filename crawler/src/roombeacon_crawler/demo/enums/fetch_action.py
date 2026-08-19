from enum import Enum


class FetchAction(str, Enum):
    PARSE = "parse"
    COOLDOWN = "cooldown"
    RETRY_LATER = "retry_later"
    STOP = "stop"
