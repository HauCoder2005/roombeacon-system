import os
from typing import Optional


def get_str(name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    raw = os.getenv(name)
    if raw is not None:
        val = raw.strip()
        if val or not required:
            return val
    if required:
        raise ValueError(f"Environment variable '{name}' is required but not set or empty.")
    return default


def get_optional_str(name: str, default: Optional[str] = None) -> Optional[str]:
    raw = os.getenv(name)
    if raw is not None:
        val = raw.strip()
        if val:
            return val
    return default


def get_int(name: str, default: Optional[int] = None, required: bool = False) -> Optional[int]:
    raw = os.getenv(name)
    if raw is not None:
        val = raw.strip()
        if val:
            try:
                return int(val)
            except ValueError:
                raise ValueError(f"Environment variable '{name}' must be an integer, got '{val}'.")
        elif required:
            raise ValueError(f"Environment variable '{name}' is required but empty.")
    if required:
        raise ValueError(f"Environment variable '{name}' is required but not set.")
    return default


def get_float(name: str, default: Optional[float] = None, required: bool = False) -> Optional[float]:
    raw = os.getenv(name)
    if raw is not None:
        val = raw.strip()
        if val:
            try:
                return float(val)
            except ValueError:
                raise ValueError(f"Environment variable '{name}' must be a float, got '{val}'.")
        elif required:
            raise ValueError(f"Environment variable '{name}' is required but empty.")
    if required:
        raise ValueError(f"Environment variable '{name}' is required but not set.")
    return default


def get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    val = raw.strip().lower()
    if val in {"true", "1", "yes", "y", "on"}:
        return True
    if val in {"false", "0", "no", "n", "off"}:
        return False
    raise ValueError(f"Environment variable '{name}' must be a boolean, got '{raw}'.")


def load_runtime_dotenv() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
