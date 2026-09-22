import re
from pathlib import Path

path = Path("crawler/src/roombeacon_crawler/repositories/local_deferred_detail_repository.py")
content = path.read_text()

# Add _cache and _dirty to __init__
content = re.sub(
    r'(def __init__\(self, base_data_dir.*?:\n(?: {8}.*?\n)*)',
    r'\1        self._cache = {}\n        self._dirty = set()\n',
    content,
    count=1
)

# Modify _load to use cache
load_impl = """
    def _load(self, source: str, target_id: str) -> dict[str, dict[str, Any]]:
        cache_key = f"{source}__{target_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]
            
        path = self._file_path(source, target_id)
        if not path.is_file():
            self._cache[cache_key] = {}
            return self._cache[cache_key]
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._cache[cache_key] = data
            elif isinstance(data, list):
                self._cache[cache_key] = {item.get("platform_post_id"): item for item in data if isinstance(item, dict) and "platform_post_id" in item}
            else:
                self._cache[cache_key] = {}
            return self._cache[cache_key]
        except Exception as exc:
            logger.warning("Deferred backlog read failed; using empty state (path=%s, error_class=%s)", path, type(exc).__name__)
            self._cache[cache_key] = {}
            return self._cache[cache_key]
"""
content = re.sub(r'    def _load\(self, source.*?return \{\}', load_impl.strip('\n'), content, flags=re.DOTALL)

# Modify _save to just mark dirty and save cache
save_impl = """
    def _save(self, source: str, target_id: str, data: dict[str, dict[str, Any]]) -> None:
        cache_key = f"{source}__{target_id}"
        self._cache[cache_key] = data
        self._dirty.add(cache_key)
        
        # Throttled flush (optional, we will rely on explicit flush)
        if len(self._dirty) > 100:  # Just a safety valve, but actually we want to flush explicitly
            pass 

    def flush(self) -> None:
        for cache_key in list(self._dirty):
            source, target_id = cache_key.split("__", 1)
            path = self._file_path(source, target_id)
            temp_file = path.with_suffix(".tmp")
            try:
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(self._cache[cache_key], f, indent=2, ensure_ascii=False)
                temp_file.replace(path)
                self._dirty.remove(cache_key)
            except Exception as exc:
                logger.error("Deferred backlog write failed (path=%s, error_class=%s)", path, type(exc).__name__)
                if temp_file.exists():
                    temp_file.unlink(missing_ok=True)
"""
content = re.sub(r'    def _save\(self, source.*?temp_file\.unlink\(missing_ok=True\)', save_impl.strip('\n'), content, flags=re.DOTALL)

path.write_text(content)
