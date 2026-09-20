import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
apps = json.loads((ROOT / "data" / "verified.json").read_text(encoding="utf-8"))
c = Counter(a["buildability"] for a in apps)
print("COUNTS", dict(c))
print("READY", c.get("build-today", 0), "of", len(apps))
print("---NON-READY---")
for a in apps:
    if a["buildability"] != "build-today":
        print(
            f"{a['id']:3} | {a['name'][:32]:32} | {a['access_model']:16} | "
            f"{a['api_type']:14} | {a['buildability']:22} | {str(a.get('main_blocker'))[:70]}"
        )
