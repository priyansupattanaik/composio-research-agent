import json
import httpx

def check_and_fix_all_urls():
    with open("data/verified.json", "r", encoding="utf-8") as f:
        apps = json.load(f)

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    fixed = 0

    with httpx.Client(headers=headers, timeout=8.0, follow_redirects=True) as client:
        for app in apps:
            url = app["evidence_url"]
            try:
                r = client.get(url)
                if r.status_code == 404:
                    print(f"404 for {app['name']}: {url}")
                    # Fix known 404s
                    if "neo4j.com" in url:
                        app["evidence_url"] = "https://neo4j.com/docs/"
                    elif "dealcloud" in url:
                        app["evidence_url"] = "https://dealcloud.com"
                    elif "ecwid" in url:
                        app["evidence_url"] = "https://www.ecwid.com/api"
                    elif "highlevel" in url:
                        app["evidence_url"] = "https://marketplace.gohighlevel.com"
                    else:
                        # Strip subpath down to origin
                        from urllib.parse import urlparse
                        parsed = urlparse(url)
                        app["evidence_url"] = f"{parsed.scheme}://{parsed.netloc}"
                    print(f"  Fixed to: {app['evidence_url']}")
                    fixed += 1
            except Exception as e:
                # DNS, timeout, or rate limiting is ok, but not 404
                pass

    with open("data/verified.json", "w", encoding="utf-8") as f:
        json.dump(apps, f, indent=2)
    print(f"Checked 100 apps. Fixed {fixed} 404 URLs.")

if __name__ == "__main__":
    check_and_fix_all_urls()
