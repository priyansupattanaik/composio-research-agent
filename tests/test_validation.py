import json
import os
import unittest
from pathlib import Path
import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent

class TestComposioResearchAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.verified_path = ROOT_DIR / "data" / "verified.json"
        cls.first_pass_path = ROOT_DIR / "data" / "first_pass.json"
        cls.patterns_path = ROOT_DIR / "data" / "patterns.json"
        cls.accuracy_path = ROOT_DIR / "data" / "accuracy_report.json"
        cls.checklist_path = ROOT_DIR / "data" / "human_review_checklist.md"
        cls.html_path = ROOT_DIR / "output" / "index.html"

        with open(cls.verified_path, "r", encoding="utf-8") as f:
            cls.apps = json.load(f)

    def test_01_total_apps_and_structure(self):
        self.assertEqual(len(self.apps), 100, "verified.json must contain exactly 100 apps")
        required_fields = [
            "id", "name", "category", "one_liner", "auth_methods", "primary_auth",
            "auth_notes", "access_model", "access_notes", "api_type", "api_breadth",
            "has_mcp", "mcp_url", "buildability", "main_blocker", "evidence_url",
            "confidence", "agent_notes", "human_verified"
        ]
        for app in self.apps:
            for field in required_fields:
                self.assertIn(field, app, f"Missing field {field} in app {app.get('name')}")
            self.assertIsNotNone(app["id"])
            self.assertIsNotNone(app["name"])
            self.assertIsNotNone(app["category"])

    def test_02_allowed_enums_and_types(self):
        ALLOWED_AUTH = ["OAuth2", "API Key", "Basic Auth", "Bearer Token", "JWT", "HMAC", "No Auth", "Other"]
        ALLOWED_ACCESS = ["self-serve", "paid-only", "contact-sales", "partner-gated", "unclear", "no-public-api"]
        ALLOWED_API = ["REST", "GraphQL", "REST+GraphQL", "gRPC", "WebSocket", "SDK-only", "No Public API", "Other"]
        ALLOWED_BREADTH = ["minimal", "medium", "large", "extensive", "unknown"]
        ALLOWED_BUILD = ["build-today", "build-paid", "build-after-outreach", "needs-research", "not-buildable"]
        ALLOWED_CONF = ["high", "medium", "low", "failed"]

        for app in self.apps:
            name = app["name"]
            self.assertIsInstance(app["auth_methods"], list, f"auth_methods must be list in {name}")
            self.assertGreater(len(app["auth_methods"]), 0, f"auth_methods must not be empty in {name}")
            for m in app["auth_methods"]:
                self.assertIn(m, ALLOWED_AUTH, f"Invalid auth_method '{m}' in {name}")
            self.assertIn(app["primary_auth"], ALLOWED_AUTH, f"Invalid primary_auth '{app['primary_auth']}' in {name}")
            self.assertIn(app["access_model"], ALLOWED_ACCESS, f"Invalid access_model '{app['access_model']}' in {name}")
            self.assertIn(app["api_type"], ALLOWED_API, f"Invalid api_type '{app['api_type']}' in {name}")
            self.assertIn(app["api_breadth"], ALLOWED_BREADTH, f"Invalid api_breadth '{app['api_breadth']}' in {name}")
            self.assertIn(app["buildability"], ALLOWED_BUILD, f"Invalid buildability '{app['buildability']}' in {name}")
            self.assertIn(app["confidence"], ALLOWED_CONF, f"Invalid confidence '{app['confidence']}' in {name}")
            self.assertIsInstance(app["has_mcp"], bool, f"has_mcp must be boolean in {name}")
            self.assertTrue(app["evidence_url"].startswith("http"), f"evidence_url must start with http in {name}")

    def test_03_logical_consistency(self):
        for app in self.apps:
            name = app["name"]
            # No build-today if contact-sales or partner-gated
            if app["access_model"] in ["contact-sales", "partner-gated"]:
                self.assertNotEqual(app["buildability"], "build-today", f"Inconsistent contact-sales with build-today in {name}")
            # Build-today must have main_blocker = null
            if app["buildability"] == "build-today":
                self.assertIsNone(app["main_blocker"], f"build-today must have null main_blocker in {name}")
            # Non build-today must have a main blocker description
            else:
                self.assertIsNotNone(app["main_blocker"], f"Non-build-today app {name} must have a main_blocker")
            # If has_mcp is true, mcp_url must start with http
            if app["has_mcp"]:
                self.assertIsNotNone(app["mcp_url"], f"has_mcp=true requires mcp_url in {name}")
                self.assertTrue(app["mcp_url"].startswith("http"), f"mcp_url must start with http in {name}")
            else:
                self.assertIsNone(app["mcp_url"], f"has_mcp=false must have null mcp_url in {name}")

    def test_04_human_verification_audit(self):
        human_verified_apps = [a for a in self.apps if a.get("human_verified")]
        self.assertEqual(len(human_verified_apps), 20, "Exactly 20 apps must be human verified")

        categories = set(a["category"] for a in self.apps)
        verified_categories = [a["category"] for a in human_verified_apps]
        for cat in categories:
            self.assertEqual(verified_categories.count(cat), 2, f"Category '{cat}' must have exactly 2 verified apps")

        for app in human_verified_apps:
            self.assertIn(app.get("human_verdict"), ["CORRECT", "WRONG", "PARTIALLY-CORRECT"])
            self.assertIsNotNone(app.get("human_notes"))
            self.assertGreater(len(app["human_notes"]), 5)

    def test_05_specific_corrections_applied(self):
        # App 51: DataForSEO was WRONG in first pass (OAuth2), corrected to Basic Auth
        app_51 = next(a for a in self.apps if a["id"] == 51)
        self.assertEqual(app_51["primary_auth"], "Basic Auth")
        self.assertIn("Basic Auth", app_51["auth_methods"])

        # App 14: Front was WRONG in first pass (self-serve), corrected to build-paid
        app_14 = next(a for a in self.apps if a["id"] == 14)
        self.assertEqual(app_14["access_model"], "paid-only")
        self.assertEqual(app_14["buildability"], "build-paid")

        # App 44: Salesforce Commerce Cloud was WRONG in first pass, corrected to contact-sales
        app_44 = next(a for a in self.apps if a["id"] == 44)
        self.assertEqual(app_44["access_model"], "contact-sales")
        self.assertEqual(app_44["buildability"], "build-after-outreach")

    def test_06_accuracy_report(self):
        with open(self.accuracy_path, "r", encoding="utf-8") as f:
            acc = json.load(f)
        self.assertEqual(acc["sample_size"], 20)
        self.assertEqual(acc["total_apps"], 100)
        self.assertEqual(acc["first_pass_accuracy"]["correct"], 14)
        self.assertEqual(acc["first_pass_accuracy"]["wrong"], 4)
        self.assertEqual(acc["first_pass_accuracy"]["partially_correct"], 2)
        self.assertEqual(acc["first_pass_accuracy"]["accuracy_pct"], 70.0)
        self.assertEqual(acc["after_verification_accuracy"]["accuracy_pct"], 100.0)

    def test_07_patterns_insights(self):
        with open(self.patterns_path, "r", encoding="utf-8") as f:
            patterns = json.load(f)
        insights = patterns.get("P8_headline_insights", [])
        self.assertEqual(len(insights), 5, "P8 must contain exactly 5 headline insights")
        for ins in insights:
            self.assertIsInstance(ins, str)
            self.assertTrue(any(ch.isdigit() for ch in ins), f"Insight missing number: {ins}")
            self.assertTrue(ins.endswith("."), f"Insight should end with a period: {ins}")

    def test_08_html_deliverable(self):
        with open(self.html_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("const APP_DATA =", html)
        self.assertIn("const PATTERNS =", html)
        self.assertIn("const ACCURACY =", html)
        self.assertIn("getHumanVerdictBadge", html)
        self.assertIn("Human Verification Audit Log (20 Sampled Apps)", html)
        self.assertGreater(len(html), 50000, "HTML file should be self-contained and substantial")

    def test_09_spot_check_evidence_urls(self):
        sample = [self.apps[i] for i in range(0, 100, 5)]
        with httpx.Client(headers={"User-Agent": "Mozilla/5.0"}, timeout=10.0, follow_redirects=True) as client:
            for a in sample:
                url = a["evidence_url"]
                try:
                    r = client.get(url)
                    status = r.status_code
                except Exception as e:
                    status = f"Err: {str(e)[:25]}"
                # Ensure no 404
                self.assertNotEqual(status, 404, f"Evidence URL 404 for {a['name']}: {url}")


if __name__ == "__main__":
    unittest.main()
