import re
from pathlib import Path

path = Path("crawler/src/roombeacon_crawler/pipeline/crawl_runner.py")
content = path.read_text()

# We want to add it at the end of `run()`, before it returns `state.bronze_records, result`
flush_code = """
        if hasattr(self.deferred_repository, "flush"):
            try:
                self.deferred_repository.flush()
            except Exception as e:
                logger.error("Error flushing deferred repository: %s", e)

        bronze_started = time.perf_counter()
"""
content = content.replace("        bronze_started = time.perf_counter()", flush_code.lstrip('\n'))

path.write_text(content)
