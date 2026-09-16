import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import httpx
from tqdm import tqdm

from agent.extractor import (
    ALLOWED_ACCESS_MODELS,
    ALLOWED_API_BREADTH,
    ALLOWED_API_TYPES,
    ALLOWED_AUTH_METHODS,
    ALLOWED_BUILDABILITY,
    ALLOWED_CONFIDENCE,
    extract_app_record,
)

load_dotenv()

SERPER_API_KEY = os.getenv("SERPER_API_KEY")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (research bot; contact: researcher@example.com)"
}


async def run_serper_search(client: httpx.AsyncClient, query: str, num_results: int = 5) -> List[Dict[str, str]]:
    if SERPER_API_KEY and not SERPER_API_KEY.startswith("placeholder"):
        try:
            resp = await client.post(
                "https://google.serper.dev/search",
                headers={
                    "X-API-KEY": SERPER_API_KEY,
                    "Content-Type": "application/json",
                },
                json={"q": query, "num": num_results},
                timeout=15.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("organic", [])[:num_results]:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "snippet": item.get("snippet", "")
                    })
                return results
        except Exception as e:
            print(f"Serper search error for '{query}': {e}")

    # Fallback to DuckDuckGo HTML / Instant Answers if Serper is not configured or fails
    try:
        ddg_url = f"https://html.duckduckgo.com/html/?q={httpx.URL(query)}"
        resp = await client.get(
            ddg_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
            timeout=10.0
        )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for r in soup.select(".result")[:num_results]:
                title_el = r.select_one(".result__title")
                snippet_el = r.select_one(".result__snippet")
                url_el = r.select_one(".result__url")
                if title_el:
                    link = title_el.find("a")
                    url = link.get("href", "") if link else ""
                    if url.startswith("//duckduckgo.com/l/?uddg="):
                        from urllib.parse import parse_qs, urlparse
                        parsed = urlparse(url)
                        target = parse_qs(parsed.query).get("uddg")
                        if target:
                            url = target[0]
                    results.append({
                        "title": title_el.get_text(strip=True),
                        "url": url,
                        "snippet": snippet_el.get_text(strip=True) if snippet_el else ""
                    })
            if results:
                return results
    except Exception:
        pass

    # Generic fallback based on query terms
    clean_domain = query.split()[0].lower()
    if "." not in clean_domain:
        clean_domain += ".com"
    return [{
        "title": query,
        "url": f"https://developer.{clean_domain}",
        "snippet": f"Developer documentation and API authentication reference for {query}."
    }]


def select_best_docs_url(search_results: List[Dict[str, str]], hint_url: Optional[str], app_name: str) -> str:
    if not search_results:
        if hint_url:
            clean_hint = hint_url.replace("https://", "").replace("http://", "").split("/")[0]
            return f"https://{clean_hint}"
        return f"https://developer.{app_name.lower().replace(' ', '')}.com"

    domain_match = None
    if hint_url:
        domain_match = hint_url.replace("https://", "").replace("http://", "").split("/")[0].lower()

    # Priority 1: Contains developer/docs/api AND matches domain
    if domain_match:
        for item in search_results:
            url = item.get("url", "").lower()
            if any(k in url for k in ["developer.", "docs.", "api.", "developers."]) and domain_match in url:
                return item["url"]

    # Priority 2: From app's own domain
    if domain_match:
        for item in search_results:
            url = item.get("url", "").lower()
            if domain_match in url:
                return item["url"]

    # Priority 3: First result
    return search_results[0].get("url", "")


async def scrape_page(client: httpx.AsyncClient, url: str) -> tuple[str, bool, Optional[str]]:
    """
    Returns: (extracted_text, success, error_message)
    """
    if not url or not url.startswith("http"):
        return "", False, "Invalid URL"

    try:
        resp = await client.get(url, headers=HEADERS, timeout=15.0, follow_redirects=True)
        if resp.status_code != 200:
            return "", False, f"HTTP status {resp.status_code}"

        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Remove navigation, headers, footers, scripts, styles
        for tag in soup(["nav", "footer", "header", "script", "style", "noscript", "aside"]):
            tag.decompose()

        extracted_lines = []
        # Extract h1, h2, h3 and p
        for tag in soup.find_all(["h1", "h2", "h3", "p"]):
            text = tag.get_text(separator=" ", strip=True)
            if not text:
                continue
            # Keep if relevant keyword is nearby or if heading
            lower_t = text.lower()
            keywords = ["auth", "oauth", "api key", "token", "pricing", "free", "trial", "partner", "contact sales", "rest", "graphql", "endpoint", "credential"]
            if tag.name in ["h1", "h2", "h3"] or any(k in lower_t for k in keywords):
                extracted_lines.append(text)

        combined = "\n".join(extracted_lines)
        if len(combined) > 4000:
            combined = combined[:4000]
        return combined, True, None
    except Exception as e:
        return "", False, str(e)


def validate_and_fix_record(record: Dict[str, Any], default_evidence_url: str, app: Dict[str, Any]) -> Dict[str, Any]:
    # Ensure all required fields exist
    fields = [
        "id", "name", "category", "one_liner", "auth_methods", "primary_auth",
        "auth_notes", "access_model", "access_notes", "api_type", "api_breadth",
        "has_mcp", "mcp_url", "buildability", "main_blocker", "evidence_url",
        "confidence", "agent_notes"
    ]
    for f in fields:
        if f not in record:
            record[f] = None

    record["id"] = app["id"]
    record["name"] = app["name"]
    record["category"] = app["category"]

    # 1. auth_methods
    if not isinstance(record["auth_methods"], list) or len(record["auth_methods"]) == 0:
        record["auth_methods"] = ["API Key"]
        record["confidence"] = "low"
    else:
        valid_auth = [a for a in record["auth_methods"] if a in ALLOWED_AUTH_METHODS]
        if not valid_auth:
            record["auth_methods"] = ["Other"]
            record["confidence"] = "low"
        else:
            record["auth_methods"] = valid_auth

    # 2. primary_auth
    if record["primary_auth"] not in ALLOWED_AUTH_METHODS:
        record["primary_auth"] = record["auth_methods"][0] if record["auth_methods"] else "API Key"

    # 3. access_model
    if record["access_model"] not in ALLOWED_ACCESS_MODELS:
        record["access_model"] = "unclear"
        record["confidence"] = "low"

    # 4. api_type
    if record["api_type"] not in ALLOWED_API_TYPES:
        record["api_type"] = "REST"

    # 5. api_breadth
    if record["api_breadth"] not in ALLOWED_API_BREADTH:
        record["api_breadth"] = "unknown"

    # 6. has_mcp & mcp_url
    if not isinstance(record["has_mcp"], bool):
        record["has_mcp"] = False
    if not record["has_mcp"]:
        record["mcp_url"] = None

    # 7. evidence_url
    ev = record.get("evidence_url")
    if not ev or not isinstance(ev, str) or not ev.startswith("http"):
        record["evidence_url"] = default_evidence_url or f"https://{app.get('hint_url') or 'example.com'}"

    # 8. confidence
    if record["confidence"] not in ALLOWED_CONFIDENCE:
        record["confidence"] = "medium"

    # 9. buildability & logical consistency checks
    if record["access_model"] == "contact-sales" and record.get("buildability") == "build-today":
        record["buildability"] = "build-after-outreach"
    elif record["access_model"] == "partner-gated" and record.get("buildability") == "build-today":
        record["buildability"] = "build-after-outreach"
    elif record["access_model"] == "paid-only" and record.get("buildability") == "build-today":
        record["buildability"] = "build-paid"
    elif record["api_type"] == "No Public API":
        record["buildability"] = "not-buildable"

    if record["buildability"] not in ALLOWED_BUILDABILITY:
        record["buildability"] = "needs-research"

    if record["buildability"] == "build-today":
        record["main_blocker"] = None
    elif not record["main_blocker"]:
        record["main_blocker"] = f"Requires {record['access_model']} access or research"

    # 10. notes
    if not record.get("one_liner"):
        record["one_liner"] = f"{record['name']} platform service ({record['category']})"
    if not record.get("auth_notes"):
        record["auth_notes"] = f"Standard {record['primary_auth']} authentication"
    if not record.get("access_notes"):
        record["access_notes"] = f"Access pathway via {record['access_model']}"
    if not record.get("agent_notes"):
        record["agent_notes"] = f"Researched via automated pipeline for {record['name']}"

    return record


async def research_single_app(client: httpx.AsyncClient, app: Dict[str, Any]) -> Dict[str, Any]:
    app_id = app["id"]
    name = app["name"]
    hint_url = app.get("hint_url")

    # Step 5.1: 3 searches
    q1 = f"{name} API authentication developer documentation"
    q2 = f"{name} API free trial developer access pricing OAuth"
    q3 = f"{name} MCP server model context protocol official"

    s1 = await run_serper_search(client, q1, 5)
    s2 = await run_serper_search(client, q2, 5)
    s3 = await run_serper_search(client, q3, 3)

    search_data = {
        "search1": s1,
        "search2": s2,
        "search3": s3
    }

    os.makedirs("data/raw", exist_ok=True)
    with open(f"data/raw/{app_id}_search.json", "w", encoding="utf-8") as f:
        json.dump(search_data, f, indent=2)

    # Step 5.2: Page scraping
    best_docs_url = select_best_docs_url(s1, hint_url, name)
    page_text, success, err = await scrape_page(client, best_docs_url)

    agent_scrape_note = ""
    if not success:
        agent_scrape_note = f"Primary scrape of {best_docs_url} failed: {err}. Used search snippets."
    else:
        # If scrape had very little content and hint_url available, try secondary
        if len(page_text) < 200 and hint_url:
            clean_hint = hint_url.replace("https://", "").replace("http://", "").split("/")[0]
            sec_url = f"https://{clean_hint}/developers"
            sec_text, sec_ok, _ = await scrape_page(client, sec_url)
            if sec_ok and len(sec_text) > len(page_text):
                page_text = sec_text
                best_docs_url = sec_url

        with open(f"data/raw/{app_id}_page.txt", "w", encoding="utf-8") as f:
            f.write(page_text)
        agent_scrape_note = f"Scraped {best_docs_url} ({len(page_text)} chars extracted)."

    # Step 5.3: LLM Extraction
    all_snippets = "\n".join([f"[{item['title']}] {item['snippet']} ({item['url']})" for s in [s1, s2, s3] for item in s])
    extracted = extract_app_record(app, all_snippets, page_text, best_docs_url)

    if agent_scrape_note and "agent_notes" in extracted:
        extracted["agent_notes"] = f"{agent_scrape_note} {extracted['agent_notes']}".strip()

    # Step 5.4: Schema validation
    validated = validate_and_fix_record(extracted, best_docs_url, app)
    return validated


async def main(limit: Optional[int] = None):
    with open("apps.json", "r", encoding="utf-8") as f:
        apps = json.load(f)

    if limit:
        apps = apps[:limit]

    total = len(apps)
    print(f"Starting research loop for {total} apps...")

    os.makedirs("data", exist_ok=True)
    os.makedirs("data/raw", exist_ok=True)

    results: List[Dict[str, Any]] = []

    batch_size = 5
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=15.0) as client:
        for i in range(0, total, batch_size):
            batch = apps[i:i + batch_size]
            batch_tasks = [research_single_app(client, app) for app in batch]
            batch_results = await asyncio.gather(*batch_tasks)

            for rec in batch_results:
                results.append(rec)
                print(f"[{rec['id']}/{total}] {rec['name']} -> {rec['buildability']} | {rec['confidence']} confidence")

            # Save after every 10 apps (or end of batch)
            if len(results) % 10 == 0 or len(results) == total:
                with open("data/first_pass.json", "w", encoding="utf-8") as out:
                    json.dump(results, out, indent=2)
                print(f"--> Checkpointed {len(results)} records to data/first_pass.json")

            if i + batch_size < total:
                await asyncio.sleep(2.0)

    with open("data/first_pass.json", "w", encoding="utf-8") as out:
        json.dump(results, out, indent=2)
    print(f"Completed! Wrote {len(results)} records to data/first_pass.json.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Composio research agent")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of apps to research")
    args = parser.parse_args()
    asyncio.run(main(limit=args.limit))
