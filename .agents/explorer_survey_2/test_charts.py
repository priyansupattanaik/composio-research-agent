import json

patterns = json.load(open("data/patterns.json", encoding="utf-8"))

print("=== Chart 1 Data (P1) ===")
p1 = patterns["P1_auth_distribution"]["primary_auth"]
for k, v in p1.items():
    print(f"  {k}: {v}")

print("\n=== Chart 2 Data (P3) ===")
p3 = patterns["P3_buildability_distribution"]
for k, v in p3.items():
    print(f"  {k}: {v}")

print("\n=== Chart 3 Data (P2) ===")
p2 = patterns["P2_access_model_by_category"]
for cat, models in p2.items():
    print(f"  {cat:35}: total={sum(models.values())}, models={models}")

print("\n=== Chart 4 Data (P7) ===")
p7 = patterns["P7_category_self_serve_rate"]
for r in p7:
    print(f"  {r['category']:35}: {r['self_serve_pct']}% ({r['self_serve_count']}/{r['total']})")
