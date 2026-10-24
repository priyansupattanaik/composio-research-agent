import json

apps = json.load(open("data/verified.json", encoding="utf-8"))

dangerous = []
for a in apps:
    url = a.get("evidence_url", "")
    for ch in ['"', "'", "<", ">", " ", "\n", "\r", "\t"]:
        if ch in url:
            dangerous.append((a["id"], a["name"], ch, url))

print(f"Total dangerous evidence_urls: {len(dangerous)}")
for d in dangerous:
    print(d)

# Also check for any missing fields in any app
required_fields = [
    "id", "name", "category", "primary_auth", "auth_methods", "access_model",
    "api_type", "api_breadth", "has_mcp", "buildability", "evidence_url",
    "one_liner", "confidence"
]
missing_fields = []
for a in apps:
    for rf in required_fields:
        if rf not in a or a[rf] is None:
            missing_fields.append((a["id"], a["name"], rf))

print(f"Total missing required fields across 100 apps: {len(missing_fields)}")
for m in missing_fields:
    print(m)
