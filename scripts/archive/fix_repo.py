import re
from pathlib import Path

path = Path("crawler/src/roombeacon_crawler/repositories/local_deferred_detail_repository.py")
content = path.read_text()

# Remove the duplicated try block from _load
content = re.sub(r'        try:\n            with open\(path, "r", encoding="utf-8"\) as f:\n                data = json\.load\(f\).*?return \{\}', '', content, flags=re.DOTALL)

path.write_text(content)
