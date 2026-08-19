from enum import Enum


class FetchStrategy(str, Enum):
    HTTP = "http"
    BROWSER = "browser"
