import re
from pathlib import Path

path = Path("crawler/src/roombeacon_crawler/repositories/local_deferred_detail_repository.py")
content = path.read_text()

# We need to completely rewrite _load to be correct.
load_code = """
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

# Replace the broken _load from '    def _load(self' to just before '    def _save'
content = re.sub(r'    def _load\(self, source: str, target_id: str\) -> dict\[str, dict\[str, Any\]\]:.*?    def _save\(self', load_code.strip('\n') + '\n\n    def _save(self', content, flags=re.DOTALL)

path.write_text(content)
