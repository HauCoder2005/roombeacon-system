from enum import Enum


class FetchAction(str, Enum):
    """Provide the demo-only FetchAction contract used by the isolated example crawler."""
    PARSE = "parse"
    COOLDOWN = "cooldown"
    RETRY_LATER = "retry_later"
    STOP = "stop"
