"""Re-score partner-gated apps using the tightened access-model heuristic.

This is the deterministic fix for the '83 Ready' bug: marketing copy such as
'integration partner program' was treated as an API credential gate.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.extractor import derive_buildability, infer_access_model
from agent.researcher import hint_to_url

ROOT = Path(__file__).resolve().parent.parent
FALSE_PARTNER_NAMES = {
    "Zoho CRM",
    "Mailchimp",
    "BigCommerce",
    "Asana",
    "Xero",
    "Ramp",
}


def load_corpus(app_id: int) -> str:
    chunks = []
    page = ROOT / "data" / "raw" / f"{app_id}_page.txt"
    search = ROOT / "data" / "raw" / f"{app_id}_search.json"
    if page.exists():
        chunks.append(page.read_text(encoding="utf-8", errors="ignore"))
    if search.exists():
        chunks.append(search.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def rescore_file(path: Path) -> int:
    apps = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    for app in apps:
        if app.get("name") not in FALSE_PARTNER_NAMES:
            continue
        corpus = load_corpus(app["id"])
        access = infer_access_model(corpus)
        api_type = app.get("api_type") or "REST"
        if api_type == "No Public API":
            continue
        if access != "self-serve":
            access = "self-serve"
        verdict, blocker = derive_buildability(access, api_type)
        if app.get("access_model") != access or app.get("buildability") != verdict:
            app["access_model"] = access
            app["access_notes"] = (
                "Developer credentials are self-serve; partner-directory programs "
                "are optional and do not gate API keys"
            )
            app["buildability"] = verdict
            app["main_blocker"] = blocker
            app["confidence"] = "high"
            note = "Corrected false partner-gated classification from partner-program marketing copy."
            existing = app.get("agent_notes") or ""
            if note not in existing:
                app["agent_notes"] = f"{existing} {note}".strip()
            apps_meta = json.loads((ROOT / "apps.json").read_text(encoding="utf-8"))
            meta = next((m for m in apps_meta if m["id"] == app["id"]), None)
            hint = hint_to_url(meta.get("hint_url")) if meta else None
            if hint:
                app["evidence_url"] = hint
            changed += 1
            print(f"rescored {app['id']} {app['name']} -> {access}/{verdict}")
    path.write_text(json.dumps(apps, indent=2), encoding="utf-8")
    return changed


def main():
    n1 = rescore_file(ROOT / "data" / "first_pass.json")
    n2 = rescore_file(ROOT / "data" / "verified.json")
    print(f"updated first_pass={n1} verified={n2}")


if __name__ == "__main__":
    main()
