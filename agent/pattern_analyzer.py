import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def compute_patterns(verified_path: str = "data/verified.json", output_path: str = "data/patterns.json"):
    if not os.path.exists(verified_path):
        print(f"Error: {verified_path} not found.")
        return

    with open(verified_path, "r", encoding="utf-8") as f:
        apps: List[Dict[str, Any]] = json.load(f)

    total = len(apps)
    if total == 0:
        print("Error: No apps in verified.json")
        return

    # P1: Auth distribution
    all_auth_counter = Counter()
    primary_auth_counter = Counter()

    for app in apps:
        primary_auth_counter[app.get("primary_auth", "Unknown")] += 1
        for m in app.get("auth_methods", []):
            clean_m = m.replace(" (unverified)", "")
            all_auth_counter[clean_m] += 1

    p1_all = {
        m: {"count": cnt, "pct": round((cnt / total) * 100.0, 1)}
        for m, cnt in all_auth_counter.most_common()
    }
    p1_primary = {
        m: {"count": cnt, "pct": round((cnt / total) * 100.0, 1)}
        for m, cnt in primary_auth_counter.most_common()
    }

    # P2: Access model by category
    categories = sorted(list({a.get("category", "") for a in apps}))
    access_models = ["self-serve", "paid-only", "contact-sales", "partner-gated", "unclear", "no-public-api"]
    
    p2_matrix = {cat: {m: 0 for m in access_models} for cat in categories}
    for app in apps:
        cat = app.get("category", "")
        model = app.get("access_model", "unclear")
        if cat in p2_matrix and model in p2_matrix[cat]:
            p2_matrix[cat][model] += 1

    # P3: Buildability distribution
    build_counter = Counter()
    for app in apps:
        build_counter[app.get("buildability", "needs-research")] += 1
    
    p3_buildability = {
        b: {"count": cnt, "pct": round((cnt / total) * 100.0, 1)}
        for b, cnt in build_counter.most_common()
    }

    # P4: Easy wins (buildability = "build-today" AND has_mcp = false)
    easy_wins = [
        app["name"] for app in apps
        if app.get("buildability") == "build-today" and not app.get("has_mcp", False)
    ]

    # P5: Most common blocker (among apps where buildability != "build-today")
    blocker_counter = Counter()
    for app in apps:
        if app.get("buildability") != "build-today":
            blocker = app.get("main_blocker")
            if blocker:
                # Group similar blockers
                b_low = blocker.lower()
                if "contact" in b_low or "sales" in b_low:
                    grouped = "Contact-sales gating"
                elif "paid" in b_low or "subscription" in b_low:
                    grouped = "Paid subscription required"
                elif "no public api" in b_low:
                    grouped = "No public API service"
                elif "partner" in b_low:
                    grouped = "Partner approval program"
                elif "underwriting" in b_low or "merchant" in b_low or "financial" in b_low:
                    grouped = "Merchant / Institutional approval"
                elif "research" in b_low or "documentation" in b_low:
                    grouped = "Thin or gated documentation"
                else:
                    grouped = blocker[:30]
                blocker_counter[grouped] += 1

    p5_blockers = [
        {"blocker": b, "count": cnt} for b, cnt in blocker_counter.most_common(5)
    ]

    # P6: MCP landscape
    mcp_counter = Counter({"has_mcp": 0, "no_mcp": 0})
    cat_mcp_counter = defaultdict(lambda: {"has_mcp": 0, "total": 0})

    for app in apps:
        has_mcp = bool(app.get("has_mcp", False))
        cat = app.get("category", "")
        if has_mcp:
            mcp_counter["has_mcp"] += 1
            cat_mcp_counter[cat]["has_mcp"] += 1
        else:
            mcp_counter["no_mcp"] += 1
        cat_mcp_counter[cat]["total"] += 1

    sorted_cat_mcp = sorted(
        cat_mcp_counter.items(),
        key=lambda x: (x[1]["has_mcp"], x[1]["has_mcp"] / max(1, x[1]["total"])),
        reverse=True
    )
    top_mcp_cat = sorted_cat_mcp[0][0] if sorted_cat_mcp else "Developer, Infra and Data Platforms"
    top_mcp_count = sorted_cat_mcp[0][1]["has_mcp"] if sorted_cat_mcp else 0

    p6_mcp = {
        "summary": dict(mcp_counter),
        "by_category": {cat: vals for cat, vals in cat_mcp_counter.items()},
        "top_category": top_mcp_cat,
        "top_category_mcp_count": top_mcp_count
    }

    # P7: Category self-serve rate
    p7_self_serve_rates = []
    cat_apps = defaultdict(list)
    for app in apps:
        cat_apps[app.get("category", "")].append(app)

    for cat, items in cat_apps.items():
        self_serve_cnt = sum(1 for a in items if a.get("access_model") == "self-serve")
        rate = round((self_serve_cnt / len(items)) * 100.0, 1)
        p7_self_serve_rates.append({
            "category": cat,
            "self_serve_count": self_serve_cnt,
            "total": len(items),
            "self_serve_pct": rate
        })

    p7_self_serve_rates = sorted(p7_self_serve_rates, key=lambda x: x["self_serve_pct"], reverse=True)

    # P8: Exactly 5 Headline insights (CRITICAL)
    # Each must be one sentence. Each must include a number.
    # Real computed numbers:
    top_auth_method = list(p1_all.keys())[0] if p1_all else "OAuth2"
    top_auth_count = p1_all[top_auth_method]["count"] if p1_all else 0
    total_mcp = mcp_counter["has_mcp"]
    most_gated_cat = p7_self_serve_rates[-1]["category"] if p7_self_serve_rates else "Finance and Fintech"
    most_gated_cnt = sum(1 for a in cat_apps[most_gated_cat] if a.get("access_model") in ["contact-sales", "partner-gated"])
    most_gated_total = len(cat_apps[most_gated_cat])
    easy_wins_count = len(easy_wins)
    top_blocker_name = p5_blockers[0]["blocker"] if p5_blockers else "contact-sales gating"
    top_blocker_count = p5_blockers[0]["count"] if p5_blockers else 0

    p8_insights = [
        f"{top_auth_method} is supported by {top_auth_count} of {total} apps, making it the most ubiquitous authentication method.",
        f"Only {total_mcp} apps have an official MCP server; {top_mcp_cat} leads with {top_mcp_count}.",
        f"{most_gated_cat} is the most gated category: {most_gated_cnt} of {most_gated_total} apps require enterprise outreach or partner approval.",
        f"{easy_wins_count} apps are build-today targets with no competing official MCP server.",
        f"The top blocker to immediate buildability is {top_blocker_name.lower()}, affecting {top_blocker_count} apps."
    ]

    patterns_output = {
        "P1_auth_distribution": {
            "all_methods": p1_all,
            "primary_auth": p1_primary
        },
        "P2_access_model_by_category": p2_matrix,
        "P3_buildability_distribution": p3_buildability,
        "P4_easy_wins": {
            "count": len(easy_wins),
            "apps": easy_wins
        },
        "P5_common_blockers": p5_blockers,
        "P6_mcp_landscape": p6_mcp,
        "P7_category_self_serve_rate": p7_self_serve_rates,
        "P8_headline_insights": p8_insights
    }

    with open(output_path, "w", encoding="utf-8") as pf:
        json.dump(patterns_output, pf, indent=2)

    print(f"Computed patterns and saved to {output_path}:")
    for i, ins in enumerate(p8_insights, 1):
        print(f"  Insight {i}: {ins}")


if __name__ == "__main__":
    compute_patterns()
