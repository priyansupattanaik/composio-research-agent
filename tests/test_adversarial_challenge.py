import json
import re
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
import unittest

ROOT_DIR = Path(__file__).resolve().parent.parent

ALLOWED_AUTH = ["OAuth2", "API Key", "Basic Auth", "Bearer Token", "JWT", "HMAC", "No Auth", "Other"]
ALLOWED_ACCESS = ["self-serve", "paid-only", "contact-sales", "partner-gated", "unclear", "no-public-api"]
ALLOWED_API = ["REST", "GraphQL", "REST+GraphQL", "gRPC", "WebSocket", "SDK-only", "No Public API", "Other"]
ALLOWED_BREADTH = ["minimal", "medium", "large", "extensive", "unknown"]
ALLOWED_BUILD = ["build-today", "build-paid", "build-after-outreach", "needs-research", "not-buildable"]
ALLOWED_CONF = ["high", "medium", "low", "failed"]
EXPECTED_CATEGORIES = [
    "AI, Research and Media-native",
    "CRM and Sales",
    "Communications and Messaging",
    "Data, SEO and Scraping",
    "Developer, Infra and Data Platforms",
    "Ecommerce",
    "Finance and Fintech",
    "Marketing, Ads, Email and Social",
    "Productivity and Project Management",
    "Support and Helpdesk"
]


class ChallengerAdversarialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(ROOT_DIR / "data" / "verified.json", "r", encoding="utf-8") as f:
            cls.verified = json.load(f)
        with open(ROOT_DIR / "data" / "first_pass.json", "r", encoding="utf-8") as f:
            cls.first_pass = json.load(f)
        with open(ROOT_DIR / "data" / "patterns.json", "r", encoding="utf-8") as f:
            cls.patterns = json.load(f)
        with open(ROOT_DIR / "data" / "accuracy_report.json", "r", encoding="utf-8") as f:
            cls.accuracy = json.load(f)
        with open(ROOT_DIR / "data" / "human_review_checklist.md", "r", encoding="utf-8") as f:
            cls.checklist_lines = f.readlines()
        with open(ROOT_DIR / "data" / "verification_log.json", "r", encoding="utf-8") as f:
            cls.vlog = json.load(f)
        with open(ROOT_DIR / "output" / "index.html", "r", encoding="utf-8") as f:
            cls.html_content = f.read()

    # =========================================================================
    # 1. CHALLENGE: data/verified.json integrity, deduplication & consistency
    # =========================================================================
    def test_challenge_01_no_duplicate_ids(self):
        ids = [a["id"] for a in self.verified]
        self.assertEqual(len(ids), 100, "Dataset must have 100 apps")
        self.assertEqual(len(set(ids)), 100, f"Duplicate IDs found: {[i for i, c in Counter(ids).items() if c > 1]}")
        self.assertEqual(sorted(ids), list(range(1, 101)), "IDs must be sequential from 1 to 100")

    def test_challenge_02_no_duplicate_names(self):
        names = [a["name"] for a in self.verified]
        self.assertEqual(len(set(names)), 100, f"Duplicate raw names found: {[n for n, c in Counter(names).items() if c > 1]}")
        normalized_names = [a["name"].strip().lower() for a in self.verified]
        self.assertEqual(len(set(normalized_names)), 100, f"Duplicate normalized names: {[n for n, c in Counter(normalized_names).items() if c > 1]}")

    def test_challenge_03_category_distribution(self):
        cats = [a["category"] for a in self.verified]
        unique_cats = sorted(list(set(cats)))
        self.assertEqual(unique_cats, sorted(EXPECTED_CATEGORIES), "Categories do not match expected 10 categories")
        cat_counts = Counter(cats)
        for cat, cnt in cat_counts.items():
            self.assertEqual(cnt, 10, f"Category '{cat}' does not have exactly 10 apps (found {cnt})")

    def test_challenge_04_schema_strictness_and_enum_adherence(self):
        expected_keys = {
            "id", "name", "category", "one_liner", "auth_methods", "primary_auth",
            "auth_notes", "access_model", "access_notes", "api_type", "api_breadth",
            "has_mcp", "mcp_url", "buildability", "main_blocker", "evidence_url",
            "confidence", "agent_notes", "human_verified", "human_verdict", "human_notes"
        }
        for app in self.verified:
            name = app["name"]
            keys = set(app.keys())
            missing = expected_keys - keys
            self.assertEqual(len(missing), 0, f"App {name} is missing keys: {missing}")

            # Validate Enum sets
            self.assertIn(app["primary_auth"], ALLOWED_AUTH, f"Illegal primary_auth in {name}: {app['primary_auth']}")
            self.assertIn(app["access_model"], ALLOWED_ACCESS, f"Illegal access_model in {name}: {app['access_model']}")
            self.assertIn(app["api_type"], ALLOWED_API, f"Illegal api_type in {name}: {app['api_type']}")
            self.assertIn(app["api_breadth"], ALLOWED_BREADTH, f"Illegal api_breadth in {name}: {app['api_breadth']}")
            self.assertIn(app["buildability"], ALLOWED_BUILD, f"Illegal buildability in {name}: {app['buildability']}")
            self.assertIn(app["confidence"], ALLOWED_CONF, f"Illegal confidence in {name}: {app['confidence']}")

            # Validate auth_methods list
            self.assertIsInstance(app["auth_methods"], list, f"auth_methods not list in {name}")
            self.assertGreater(len(app["auth_methods"]), 0, f"auth_methods empty in {name}")
            for m in app["auth_methods"]:
                self.assertIn(m, ALLOWED_AUTH, f"Illegal auth method '{m}' in {name}")
                self.assertNotIn("(unverified)", m, f"Unverified tag remains in auth_method '{m}' in {name}")

            # Primary auth must be member of auth_methods
            self.assertIn(app["primary_auth"], app["auth_methods"], f"primary_auth '{app['primary_auth']}' not in auth_methods {app['auth_methods']} for {name}")

    def test_challenge_05_url_validity_and_cleanliness(self):
        for app in self.verified:
            name = app["name"]
            url = app["evidence_url"]
            self.assertTrue(url.startswith("http://") or url.startswith("https://"), f"Bad scheme in evidence_url: {url} ({name})")
            parsed = urllib.parse.urlparse(url)
            self.assertTrue(bool(parsed.netloc), f"Empty host in evidence_url: {url} ({name})")
            self.assertNotIn(" ", url, f"Whitespace in evidence_url: {url} ({name})")
            self.assertNotIn("(", url, f"Unescaped markdown in evidence_url: {url} ({name})")
            self.assertNotIn(")", url, f"Unescaped markdown in evidence_url: {url} ({name})")

            # Check mcp_url
            if app["has_mcp"]:
                murl = app["mcp_url"]
                self.assertIsNotNone(murl, f"mcp_url is None when has_mcp is True ({name})")
                self.assertTrue(murl.startswith("http://") or murl.startswith("https://"), f"Bad mcp_url scheme: {murl} ({name})")
                m_parsed = urllib.parse.urlparse(murl)
                self.assertTrue(bool(m_parsed.netloc), f"Empty host in mcp_url: {murl} ({name})")
            else:
                self.assertIsNone(app["mcp_url"], f"mcp_url must be None when has_mcp is False ({name})")

    def test_challenge_06_cross_field_logical_integrity(self):
        for app in self.verified:
            name = app["name"]
            access = app["access_model"]
            build = app["buildability"]
            blocker = app["main_blocker"]

            # Contradiction: contact-sales or partner-gated cannot be build-today
            if access in ["contact-sales", "partner-gated"]:
                self.assertNotEqual(build, "build-today", f"Contradiction: access '{access}' but buildability 'build-today' for {name}")

            # Contradiction: no-public-api cannot be build-today or build-paid
            if access == "no-public-api":
                self.assertEqual(build, "not-buildable", f"no-public-api must be not-buildable, got '{build}' in {name}")

            # Contradiction: build-today MUST have main_blocker = null
            if build == "build-today":
                self.assertIsNone(blocker, f"build-today must have null main_blocker, got '{blocker}' in {name}")
            else:
                self.assertIsNotNone(blocker, f"Non build-today app {name} ({build}) must specify main_blocker")
                self.assertGreater(len(str(blocker).strip()), 3, f"Empty or trivial blocker in {name}")

            # Human verified flags
            if app["human_verified"]:
                self.assertIn(app["human_verdict"], ["CORRECT", "WRONG", "PARTIALLY-CORRECT"], f"Invalid human verdict in {name}")
                self.assertIsNotNone(app["human_notes"], f"Null human notes in verified app {name}")
                self.assertGreater(len(app["human_notes"].strip()), 5, f"Too short human notes in {name}")
            else:
                self.assertIsNone(app["human_verdict"], f"Unverified app {name} should have null human_verdict")
                self.assertIsNone(app["human_notes"], f"Unverified app {name} should have null human_notes")

    # =========================================================================
    # 2. CHALLENGE: data/patterns.json 100% mathematical consistency
    # =========================================================================
    def test_challenge_07_recompute_p1_auth_distribution(self):
        total = len(self.verified)
        all_counter = Counter()
        primary_counter = Counter()

        for a in self.verified:
            primary_counter[a["primary_auth"]] += 1
            for m in a["auth_methods"]:
                all_counter[m] += 1

        p1_data = self.patterns["P1_auth_distribution"]
        # Compare all_methods
        for m, cnt in all_counter.items():
            self.assertIn(m, p1_data["all_methods"])
            self.assertEqual(cnt, p1_data["all_methods"][m]["count"])
            expected_pct = round((cnt / total) * 100.0, 1)
            self.assertEqual(expected_pct, p1_data["all_methods"][m]["pct"])

        # Compare primary_auth
        for m, cnt in primary_counter.items():
            self.assertIn(m, p1_data["primary_auth"])
            self.assertEqual(cnt, p1_data["primary_auth"][m]["count"])
            expected_pct = round((cnt / total) * 100.0, 1)
            self.assertEqual(expected_pct, p1_data["primary_auth"][m]["pct"])

    def test_challenge_08_recompute_p2_access_model_by_category(self):
        p2_data = self.patterns["P2_access_model_by_category"]
        expected_matrix = defaultdict(lambda: Counter())

        for a in self.verified:
            expected_matrix[a["category"]][a["access_model"]] += 1

        total_cells_sum = 0
        for cat in EXPECTED_CATEGORIES:
            self.assertIn(cat, p2_data, f"Category '{cat}' missing in P2 matrix")
            for model in ALLOWED_ACCESS:
                actual = p2_data[cat].get(model, 0)
                expected = expected_matrix[cat][model]
                self.assertEqual(actual, expected, f"P2 mismatch for {cat} / {model}: expected {expected}, got {actual}")
                total_cells_sum += actual

        self.assertEqual(total_cells_sum, 100, "P2 matrix must sum to 100 total apps")

    def test_challenge_09_recompute_p3_buildability_distribution(self):
        total = len(self.verified)
        build_counter = Counter(a["buildability"] for a in self.verified)
        p3_data = self.patterns["P3_buildability_distribution"]

        self.assertEqual(sum(build_counter.values()), 100)
        for b, cnt in build_counter.items():
            self.assertIn(b, p3_data, f"Buildability '{b}' missing in P3")
            self.assertEqual(cnt, p3_data[b]["count"])
            expected_pct = round((cnt / total) * 100.0, 1)
            self.assertEqual(expected_pct, p3_data[b]["pct"])

    def test_challenge_10_recompute_p4_easy_wins(self):
        expected_easy_wins = [
            a["name"] for a in self.verified
            if a["buildability"] == "build-today" and not a["has_mcp"]
        ]
        p4_data = self.patterns["P4_easy_wins"]
        self.assertEqual(p4_data["count"], len(expected_easy_wins))
        self.assertEqual(p4_data["apps"], expected_easy_wins)

    def test_challenge_11_recompute_p5_common_blockers(self):
        blocker_counter = Counter()
        for a in self.verified:
            if a["buildability"] != "build-today":
                blocker = a.get("main_blocker")
                if blocker:
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

        top_5 = [{"blocker": b, "count": cnt} for b, cnt in blocker_counter.most_common(5)]
        p5_data = self.patterns["P5_common_blockers"]
        self.assertEqual(p5_data, top_5)

    def test_challenge_12_recompute_p6_mcp_landscape(self):
        p6_data = self.patterns["P6_mcp_landscape"]
        has_mcp_cnt = sum(1 for a in self.verified if a["has_mcp"])
        no_mcp_cnt = sum(1 for a in self.verified if not a["has_mcp"])

        self.assertEqual(p6_data["summary"]["has_mcp"], has_mcp_cnt)
        self.assertEqual(p6_data["summary"]["no_mcp"], no_mcp_cnt)
        self.assertEqual(has_mcp_cnt + no_mcp_cnt, 100)

        # By category
        for cat in EXPECTED_CATEGORIES:
            cat_apps = [a for a in self.verified if a["category"] == cat]
            expected_mcp = sum(1 for a in cat_apps if a["has_mcp"])
            actual = p6_data["by_category"][cat]
            self.assertEqual(actual["has_mcp"], expected_mcp)
            self.assertEqual(actual["total"], len(cat_apps))

    def test_challenge_13_recompute_p7_self_serve_rates(self):
        p7_data = self.patterns["P7_category_self_serve_rate"]
        self.assertEqual(len(p7_data), 10, "P7 must contain 10 categories")

        for item in p7_data:
            cat = item["category"]
            cat_apps = [a for a in self.verified if a["category"] == cat]
            expected_cnt = sum(1 for a in cat_apps if a["access_model"] == "self-serve")
            expected_total = len(cat_apps)
            expected_pct = round((expected_cnt / expected_total) * 100.0, 1)

            self.assertEqual(item["self_serve_count"], expected_cnt)
            self.assertEqual(item["total"], expected_total)
            self.assertEqual(item["self_serve_pct"], expected_pct)

        # Check sorted order
        pcts = [item["self_serve_pct"] for item in p7_data]
        self.assertEqual(pcts, sorted(pcts, reverse=True), "P7 items must be sorted descending by self_serve_pct")

    def test_challenge_14_recompute_p8_headline_insights_truth(self):
        p8_data = self.patterns["P8_headline_insights"]
        self.assertEqual(len(p8_data), 5, "P8 must contain exactly 5 headline insights")

        for s in p8_data:
            self.assertTrue(s.endswith("."), f"Sentence must end with a period: {s}")
            self.assertTrue(any(ch.isdigit() for ch in s), f"Sentence must contain a number: {s}")

        # Insight 1: Auth distribution claim
        match1 = re.search(r"(\w+) is supported by (\d+) of (\d+) apps", p8_data[0])
        self.assertIsNotNone(match1, f"Failed regex on insight 1: {p8_data[0]}")
        auth_name, count_str, total_str = match1.groups()
        self.assertEqual(auth_name, "OAuth2")
        self.assertEqual(int(count_str), 91)
        self.assertEqual(int(total_str), 100)

        # Insight 2: MCP claim
        match2 = re.search(r"Only (\d+) apps have an official MCP server; (.+) leads with (\d+)\.", p8_data[1])
        self.assertIsNotNone(match2, f"Failed regex on insight 2: {p8_data[1]}")
        total_mcp, top_cat, top_mcp_cnt = match2.groups()
        self.assertEqual(int(total_mcp), 4)
        self.assertEqual(top_cat, "Developer, Infra and Data Platforms")
        self.assertEqual(int(top_mcp_cnt), 3)

        # Insight 3: Gated category claim
        match3 = re.search(r"(.+) is the most gated category: (\d+) of (\d+) apps require enterprise outreach or partner approval\.", p8_data[2])
        self.assertIsNotNone(match3, f"Failed regex on insight 3: {p8_data[2]}")
        cat_name, gated_cnt, total_cat = match3.groups()
        self.assertEqual(cat_name, "Finance and Fintech")
        self.assertEqual(int(gated_cnt), 4)
        self.assertEqual(int(total_cat), 10)

        # Insight 4: Easy wins claim
        match4 = re.search(r"(\d+) apps are build-today targets with no competing official MCP server\.", p8_data[3])
        self.assertIsNotNone(match4, f"Failed regex on insight 4: {p8_data[3]}")
        easy_cnt = int(match4.group(1))
        self.assertEqual(easy_cnt, 79)

        # Insight 5: Blocker claim
        match5 = re.search(r"The top blocker to immediate buildability is (.+), affecting (\d+) apps\.", p8_data[4])
        self.assertIsNotNone(match5, f"Failed regex on insight 5: {p8_data[4]}")
        blocker_text, blocker_cnt = match5.groups()
        self.assertEqual(int(blocker_cnt), 11)

    # =========================================================================
    # 3. CHALLENGE: data/accuracy_report.json vs data/human_review_checklist.md
    # =========================================================================
    def test_challenge_15_human_review_checklist_math(self):
        rows = []
        for line in self.checklist_lines:
            line = line.strip()
            if not line.startswith("|") or line.startswith("| #") or line.startswith("|---"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 9:
                rows.append({
                    "id": int(parts[1]),
                    "app": parts[2],
                    "category": parts[3],
                    "verdict": parts[7].upper(),
                    "notes": parts[8]
                })

        self.assertEqual(len(rows), 20, "Human review checklist must have exactly 20 sampled apps")

        cats = [r["category"] for r in rows]
        cat_counter = Counter(cats)
        self.assertEqual(len(cat_counter), 10, "Must cover all 10 categories")
        for cat, cnt in cat_counter.items():
            self.assertEqual(cnt, 2, f"Category '{cat}' must have 2 reviews, got {cnt}")

        verdict_counts = Counter(r["verdict"] for r in rows)
        c_cnt = verdict_counts["CORRECT"]
        w_cnt = verdict_counts["WRONG"]
        p_cnt = verdict_counts["PARTIALLY-CORRECT"]

        self.assertEqual(c_cnt, 14, f"Expected 14 CORRECT, got {c_cnt}")
        self.assertEqual(w_cnt, 4, f"Expected 4 WRONG, got {w_cnt}")
        self.assertEqual(p_cnt, 2, f"Expected 2 PARTIALLY-CORRECT, got {p_cnt}")

        first_pass_acc = round((c_cnt / len(rows)) * 100.0, 1)
        self.assertEqual(first_pass_acc, 70.0)

        # Check accuracy_report.json
        self.assertEqual(self.accuracy["sample_size"], 20)
        self.assertEqual(self.accuracy["total_apps"], 100)
        self.assertEqual(self.accuracy["first_pass_accuracy"]["correct"], 14)
        self.assertEqual(self.accuracy["first_pass_accuracy"]["wrong"], 4)
        self.assertEqual(self.accuracy["first_pass_accuracy"]["partially_correct"], 2)
        self.assertEqual(self.accuracy["first_pass_accuracy"]["accuracy_pct"], 70.0)
        self.assertEqual(self.accuracy["after_verification_accuracy"]["correct"], 20)
        self.assertEqual(self.accuracy["after_verification_accuracy"]["accuracy_pct"], 100.0)

    # =========================================================================
    # 4. CHALLENGE: Standalone deliverable inlining and zero data drift
    # =========================================================================
    def test_challenge_16_html_inlining_integrity(self):
        # Extract APP_DATA from output/index.html line
        app_line = next(l for l in self.html_content.splitlines() if "const APP_DATA =" in l)
        json_app_str = app_line.split("const APP_DATA =", 1)[1].strip().rstrip(";")
        inlined_apps = json.loads(json_app_str)
        self.assertEqual(len(inlined_apps), 100)
        self.assertEqual(inlined_apps, self.verified, "Inlined APP_DATA drifted from data/verified.json")

        # Extract PATTERNS from output/index.html line
        pat_line = next(l for l in self.html_content.splitlines() if "const PATTERNS =" in l)
        json_pat_str = pat_line.split("const PATTERNS =", 1)[1].strip().rstrip(";")
        inlined_patterns = json.loads(json_pat_str)
        self.assertEqual(inlined_patterns, self.patterns, "Inlined PATTERNS drifted from data/patterns.json")

        # Extract ACCURACY from output/index.html line
        acc_line = next(l for l in self.html_content.splitlines() if "const ACCURACY =" in l)
        json_acc_str = acc_line.split("const ACCURACY =", 1)[1].strip().rstrip(";")
        inlined_accuracy = json.loads(json_acc_str)
        self.assertEqual(inlined_accuracy, self.accuracy, "Inlined ACCURACY drifted from data/accuracy_report.json")

    # =========================================================================
    # 5. CHALLENGE: Verification Log Integrity
    # =========================================================================
    def test_challenge_17_verification_log_integrity(self):
        self.assertEqual(len(self.vlog), 100, "verification_log.json must have 100 entries")
        vlog_ids = [v["app_id"] for v in self.vlog]
        self.assertEqual(vlog_ids, list(range(1, 101)), "verification_log IDs must be 1 to 100")
        human_v_entries = [v for v in self.vlog if v.get("human_verified")]
        self.assertEqual(len(human_v_entries), 20, "Exactly 20 verification log entries must be human verified")


if __name__ == "__main__":
    unittest.main()
