"""Re-extract remaining non-build-today apps with NVIDIA Nemotron.

Human CORRECT verdicts are left untouched. Prints redacted provider errors only.
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

from agent.extractor import extract_app_record, nvidia_api_key

ROOT = Path(__file__).resolve().parent.parent
HUMAN_CORRECT_LOCK = {50, 59, 84, 90, 91}
HUMAN_WRONG_LOCK = {14, 44, 92}
NO_PUBLIC_API_LOCK = {50, 58, 91}


def load_corpus(app_id: int):
    page = ROOT / "data" / "raw" / f"{app_id}_page.txt"
    search = ROOT / "data" / "raw" / f"{app_id}_search.json"
    page_text = page.read_text(encoding="utf-8", errors="ignore") if page.exists() else ""
    snippets = search.read_text(encoding="utf-8", errors="ignore") if search.exists() else ""
    return snippets, page_text


def main():
    if not nvidia_api_key():
        print("NVIDIA_API_KEY missing; skip live re-extract")
        return 2
    apps_meta = {a["id"]: a for a in json.loads((ROOT / "apps.json").read_text(encoding="utf-8"))}
    verified = json.loads((ROOT / "data" / "verified.json").read_text(encoding="utf-8"))
    first_pass = json.loads((ROOT / "data" / "first_pass.json").read_text(encoding="utf-8"))
    fp_map = {a["id"]: a for a in first_pass}
    changed = 0
    for app in verified:
        if app.get("buildability") == "build-today":
            continue
        if app["id"] in HUMAN_CORRECT_LOCK | HUMAN_WRONG_LOCK | NO_PUBLIC_API_LOCK:
            print(f"lock  {app['id']:3} {app['name']}: keep {app['buildability']}")
            continue
        meta = apps_meta[app["id"]]
        snippets, page_text = load_corpus(app["id"])
        print(f"llm   {app['id']:3} {app['name']}: calling Nemotron...")
        record = extract_app_record(
            meta,
            snippets,
            page_text,
            app.get("evidence_url") or "",
        )
        print(
            f"      -> access={record.get('access_model')} "
            f"api={record.get('api_type')} "
            f"build={record.get('buildability')} "
            f"conf={record.get('confidence')}"
        )
        # Only promote into build-today when Nemotron and current API type agree REST-family exists
        if record.get("buildability") == "build-today" and record.get("access_model") == "self-serve":
            for target in (app, fp_map.get(app["id"])):
                if not target:
                    continue
                for key in (
                    "access_model", "access_notes", "api_type", "api_breadth",
                    "auth_methods", "primary_auth", "auth_notes", "buildability",
                    "main_blocker", "evidence_url", "confidence", "agent_notes",
                    "has_mcp", "mcp_url",
                ):
                    if key in record:
                        target[key] = record[key]
            changed += 1
            print("      APPLIED build-today")
        else:
            print("      kept existing classification")
    (ROOT / "data" / "verified.json").write_text(json.dumps(verified, indent=2), encoding="utf-8")
    (ROOT / "data" / "first_pass.json").write_text(json.dumps(first_pass, indent=2), encoding="utf-8")
    print(f"applied_promotions={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
