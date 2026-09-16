import argparse
import asyncio
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
from bs4 import BeautifulSoup
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (research bot; contact: researcher@example.com)"
}


def downgrade_confidence(conf: str) -> str:
    mapping = {
        "high": "medium",
        "medium": "low",
        "low": "failed",
        "failed": "failed"
    }
    return mapping.get(conf, "low")


async def check_url_liveness(client: httpx.AsyncClient, url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    try:
        # First try HEAD, if 405 or 403 try GET
        resp = await client.head(url, headers=HEADERS, timeout=10.0, follow_redirects=True)
        if resp.status_code in [200, 301, 302, 307, 308]:
            return True
        if resp.status_code in [403, 405]:
            resp2 = await client.get(url, headers=HEADERS, timeout=10.0, follow_redirects=True)
            return resp2.status_code in [200, 301, 302, 307, 308]
        return False
    except Exception:
        return False


def check_auth_keywords(app_id: int, auth_methods: List[str]) -> Tuple[List[str], List[str]]:
    raw_page_path = f"data/raw/{app_id}_page.txt"
    raw_search_path = f"data/raw/{app_id}_search.json"
    
    text_corpus = ""
    if os.path.exists(raw_page_path):
        with open(raw_page_path, "r", encoding="utf-8", errors="ignore") as f:
            text_corpus += f.read().lower() + "\n"
    if os.path.exists(raw_search_path):
        with open(raw_search_path, "r", encoding="utf-8", errors="ignore") as f:
            text_corpus += f.read().lower() + "\n"

    unverified = []
    updated_methods = []

    for method in auth_methods:
        clean_method = method.replace(" (unverified)", "")
        m_lower = clean_method.lower()
        matched = False

        if m_lower == "oauth2":
            matched = ("oauth" in text_corpus or "oauth 2" in text_corpus)
        elif m_lower == "api key":
            matched = ("api key" in text_corpus or "apikey" in text_corpus or "x-api-key" in text_corpus or "token" in text_corpus)
        elif m_lower == "basic auth":
            matched = ("basic " in text_corpus or ("username" in text_corpus and "password" in text_corpus))
        elif m_lower == "bearer token":
            matched = ("bearer" in text_corpus)
        elif m_lower == "jwt":
            matched = ("jwt" in text_corpus or "json web token" in text_corpus)
        elif m_lower == "hmac":
            matched = ("hmac" in text_corpus or "signature" in text_corpus)
        elif m_lower == "no auth":
            matched = True
        else:
            matched = True

        if not matched:
            unverified.append(clean_method)
            updated_methods.append(f"{clean_method} (unverified)")
        else:
            updated_methods.append(clean_method)

    return unverified, updated_methods


async def check_mcp(client: httpx.AsyncClient, mcp_url: str) -> bool:
    if not mcp_url or not mcp_url.startswith("http"):
        return False
    try:
        resp = await client.get(mcp_url, headers=HEADERS, timeout=10.0, follow_redirects=True)
        if resp.status_code != 200:
            return False
        text = resp.text.lower()
        return ("mcp" in text or "model context protocol" in text)
    except Exception:
        return False


def check_pricing_conflict(app_id: int, app_name: str, access_model: str) -> bool:
    if access_model != "self-serve":
        return False
    raw_search_path = f"data/raw/{app_id}_search.json"
    if not os.path.exists(raw_search_path):
        return False
    with open(raw_search_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read().lower()

    if any(k in content for k in ["contact sales", "enterprise only", "talk to sales", "request a quote"]):
        # Possible conflict if self-serve was claimed
        return True
    return False


async def run_auto_verification():
    first_pass_path = "data/first_pass.json"
    if not os.path.exists(first_pass_path):
        print(f"Error: {first_pass_path} not found.")
        return

    with open(first_pass_path, "r", encoding="utf-8") as f:
        apps = json.load(f)

    print(f"Running auto-verification on {len(apps)} apps...")
    verification_log = []
    flags_count = 0
    auto_corrections_count = 0

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=12.0) as client:
        for app in apps:
            app_id = app["id"]
            app_name = app["name"]
            flags = []
            auto_corrected = []

            # Check A: URL liveness
            ev_url = app.get("evidence_url")
            is_alive = await check_url_liveness(client, ev_url)
            if not is_alive:
                flags.append("dead_evidence_url")
                prev_conf = app.get("confidence", "high")
                app["confidence"] = downgrade_confidence(prev_conf)
                auto_corrected.append(f"Downgraded confidence from {prev_conf} to {app['confidence']} due to dead URL")

            # Check B: Auth keyword cross-check
            unverified_auths, updated_auth_methods = check_auth_keywords(app_id, app.get("auth_methods", []))
            if unverified_auths:
                flags.append("unverified_auth_claim")
                app["auth_methods"] = updated_auth_methods
                auto_corrected.append(f"Flagged unverified auth: {', '.join(unverified_auths)}")

            # Check C: MCP verification
            if app.get("has_mcp"):
                mcp_ok = await check_mcp(client, app.get("mcp_url"))
                if not mcp_ok:
                    flags.append("mcp_claim_rejected")
                    app["has_mcp"] = False
                    app["mcp_url"] = None
                    auto_corrected.append("has_mcp set to false; mcp_url cleared")

            # Check D: Access model vs price page
            has_pricing_conflict = check_pricing_conflict(app_id, app_name, app.get("access_model"))
            if has_pricing_conflict:
                flags.append("possible_access_model_error")
                prev_conf = app.get("confidence", "high")
                app["confidence"] = downgrade_confidence(prev_conf)
                auto_corrected.append(f"Downgraded confidence to {app['confidence']} due to possible contact-sales requirement")

            requires_human_review = bool(flags or app.get("confidence") in ["low", "failed"])

            log_entry = {
                "app_id": app_id,
                "app_name": app_name,
                "flags": flags,
                "auto_corrected": auto_corrected,
                "requires_human_review": requires_human_review,
                "human_verified": False,
                "human_notes": None,
                "human_verdict": None
            }
            verification_log.append(log_entry)
            flags_count += len(flags)
            auto_corrections_count += len(auto_corrected)

    # Save verification_log.json
    with open("data/verification_log.json", "w", encoding="utf-8") as f:
        json.dump(verification_log, f, indent=2)

    # Update first_pass with any corrections applied
    with open("data/first_pass.json", "w", encoding="utf-8") as f:
        json.dump(apps, f, indent=2)

    print(f"Auto-verification complete!")
    print(f"Flags raised: {flags_count}")
    print(f"Auto-corrections applied: {auto_corrections_count}")
    print(f"Apps requiring human review: {sum(1 for v in verification_log if v['requires_human_review'])}")

    # Now generate human review checklist (Section 7.2)
    generate_human_checklist(apps, verification_log)


def generate_human_checklist(apps: List[Dict[str, Any]], verification_log: List[Dict[str, Any]]):
    # Group by category
    categories = {}
    app_map = {a["id"]: a for a in apps}
    log_map = {v["app_id"]: v for v in verification_log}

    for a in apps:
        cat = a["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(a)

    selected_ids = []
    # Select 2 apps from each category (10 x 2 = 20)
    for cat, cat_apps in categories.items():
        # Score apps: prioritize lowest confidence and highest flags
        def priority_score(item):
            v = log_map.get(item["id"], {})
            conf = item.get("confidence", "high")
            conf_score = {"failed": 4, "low": 3, "medium": 2, "high": 1}.get(conf, 1)
            flags_score = len(v.get("flags", []))
            return (conf_score * 10 + flags_score)

        sorted_cat_apps = sorted(cat_apps, key=priority_score, reverse=True)
        selected_ids.extend([a["id"] for a in sorted_cat_apps[:2]])

    selected_ids = sorted(selected_ids)

    # Build markdown checklist table
    md_lines = [
        "# Human Review Checklist (20 Apps Sample)",
        "",
        "This checklist validates agent research across 10 categories (2 apps each).",
        "",
        "| # | App | Category | Check | Agent Answer | Evidence URL | Human Verdict | Notes |",
        "|---|-----|----------|-------|--------------|--------------|---------------|-------|"
    ]

    for app_id in selected_ids:
        app = app_map[app_id]
        vlog = log_map[app_id]
        agent_ans = f"Auth: {', '.join(app['auth_methods'])}; Access: {app['access_model']}; Verdict: {app['buildability']}"
        md_lines.append(
            f"| {app_id} | {app['name']} | {app['category']} | Auth + Access + Verdict | {agent_ans} | [{app['name']} Docs]({app['evidence_url']}) | | |"
        )

    checklist_path = "data/human_review_checklist.md"
    with open(checklist_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")

    print(f"Generated human review checklist at {checklist_path} with {len(selected_ids)} apps.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run verifier")
    parser.add_argument("--auto", action="store_true", help="Run automated verification checks")
    args = parser.parse_args()
    if args.auto:
        asyncio.run(run_auto_verification())
    else:
        asyncio.run(run_auto_verification())
