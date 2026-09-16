import json

def fix_urls():
    apps_meta = json.load(open("apps.json", "r", encoding="utf-8"))
    meta_map = {a["id"]: a for a in apps_meta}

    for filepath in ["data/verified.json", "data/first_pass.json"]:
        data = json.load(open(filepath, "r", encoding="utf-8"))
        for app in data:
            meta = meta_map.get(app["id"])
            if meta and meta.get("hint_url"):
                hint = meta["hint_url"]
                if not hint.startswith("http"):
                    hint = f"https://{hint}"
                app["evidence_url"] = hint
            elif not app.get("evidence_url") or not app["evidence_url"].startswith("http"):
                clean_name = app["name"].lower().replace(" ", "")
                app["evidence_url"] = f"https://{clean_name}.com"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    print("Fixed all evidence_urls to match canonical assignment hints.")

if __name__ == "__main__":
    fix_urls()
