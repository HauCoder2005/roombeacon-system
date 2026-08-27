from enum import Enum


class FetchStrategy(str, Enum):
    """Provide the demo-only FetchStrategy contract used by the isolated example crawler."""
    HTTP = "http"
    BROWSER = "browser"
