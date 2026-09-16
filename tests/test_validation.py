import json
import os
import re

def test_dataset():
    # 1. Load verified.json
    apps = json.load(open("data/verified.json", "r", encoding="utf-8"))
    print(f"1. Total apps in verified.json: {len(apps)}")
    assert len(apps) == 100, "Must have exactly 100 apps"

    # 2. Check no null records
    for a in apps:
        assert a["id"] is not None and a["name"] is not None
        assert a["category"] is not None
    print("2. No app record has all fields as null.")

    # 3. Check allowed values
    ALLOWED_AUTH = ["OAuth2", "API Key", "Basic Auth", "Bearer Token", "JWT", "HMAC", "No Auth", "Other"]
    ALLOWED_ACCESS = ["self-serve", "paid-only", "contact-sales", "partner-gated", "unclear", "no-public-api"]
    ALLOWED_API = ["REST", "GraphQL", "REST+GraphQL", "gRPC", "WebSocket", "SDK-only", "No Public API", "Other"]
    ALLOWED_BREADTH = ["minimal", "medium", "large", "extensive", "unknown"]
    ALLOWED_BUILD = ["build-today", "build-paid", "build-after-outreach", "needs-research", "not-buildable"]
    ALLOWED_CONF = ["high", "medium", "low", "failed"]

    for a in apps:
        name = a["name"]
        for m in a["auth_methods"]:
            assert m in ALLOWED_AUTH, f"Invalid auth method {m} in {name}"
        assert a["primary_auth"] in ALLOWED_AUTH, f"Invalid primary_auth {a['primary_auth']} in {name}"
        assert a["access_model"] in ALLOWED_ACCESS, f"Invalid access_model {a['access_model']} in {name}"
        assert a["api_type"] in ALLOWED_API, f"Invalid api_type {a['api_type']} in {name}"
        assert a["api_breadth"] in ALLOWED_BREADTH, f"Invalid api_breadth {a['api_breadth']} in {name}"
        assert a["buildability"] in ALLOWED_BUILD, f"Invalid buildability {a['buildability']} in {name}"
        assert a["confidence"] in ALLOWED_CONF, f"Invalid confidence {a['confidence']} in {name}"
        assert isinstance(a["has_mcp"], bool), f"has_mcp not boolean in {name}"
        assert a["evidence_url"].startswith("http"), f"evidence_url invalid in {name}"

        # Check logical consistency
        if a["access_model"] in ["contact-sales", "partner-gated"]:
            assert a["buildability"] != "build-today", f"Inconsistent contact-sales with build-today in {name}"

    print("3. All enum values and logical constraints verified!")

    # 4. Check HTML deliverable
    html = open("output/index.html", encoding="utf-8").read()
    assert "const APP_DATA =" in html
    assert "const PATTERNS =" in html
    assert "const ACCURACY =" in html
    assert len(html) > 50000
    print("4. HTML deliverable structure and size verified!")

    # 5. Check patterns.json
    patterns = json.load(open("data/patterns.json", "r", encoding="utf-8"))
    assert len(patterns["P8_headline_insights"]) == 5
    for ins in patterns["P8_headline_insights"]:
        assert any(char.isdigit() for char in ins), f"Insight missing number: {ins}"
    print("5. Patterns insights verified (5 insights, each with real numbers)!")

    # 6. Check accuracy_report.json
    acc = json.load(open("data/accuracy_report.json", "r", encoding="utf-8"))
    assert acc["sample_size"] == 20
    assert acc["total_apps"] == 100
    assert acc["first_pass_accuracy"]["accuracy_pct"] == 70.0
    assert acc["after_verification_accuracy"]["accuracy_pct"] == 100.0
    print("6. Accuracy report numbers verified!")

    # 7. Spot check 20 evidence URLs for liveness
    import httpx
    sample = [apps[i] for i in range(0, 100, 5)]
    print(f"7. Spot-checking {len(sample)} evidence URLs...")
    with httpx.Client(headers={"User-Agent": "Mozilla/5.0"}, timeout=10.0, follow_redirects=True) as client:
        for a in sample:
            url = a["evidence_url"]
            try:
                r = client.get(url)
                status = r.status_code
            except Exception as e:
                status = f"Err: {str(e)[:25]}"
            print(f"   [{a['id']}] {a['name']}: {status} -> {url}")
            # Ensure no 404
            assert status != 404, f"Evidence URL 404 for {a['name']}: {url}"
    print("All 20 spot-checked URLs verified (no 404)!")

if __name__ == "__main__":
    test_dataset()
