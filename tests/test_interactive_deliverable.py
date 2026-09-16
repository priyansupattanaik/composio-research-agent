import asyncio
import json
import shutil
import subprocess
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path
import websockets

ROOT_DIR = Path(__file__).resolve().parent.parent
HTML_PATH = ROOT_DIR / "output" / "index.html"
EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


class CDPClient:
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.ws = None
        self.msg_id = 0
        self.pending_responses = {}
        self.console_messages = []
        self.console_errors = []
        self.exceptions = []
        self.network_failures = []
        self.listener_task = None
        self.is_running = False

    async def connect(self):
        self.ws = await websockets.connect(self.ws_url, max_size=25 * 1024 * 1024)
        self.is_running = True
        self.listener_task = asyncio.create_task(self._listen())

    async def _listen(self):
        try:
            while self.is_running:
                raw = await self.ws.recv()
                msg = json.loads(raw)
                if "id" in msg:
                    future = self.pending_responses.pop(msg["id"], None)
                    if future and not future.done():
                        future.set_result(msg)
                elif "method" in msg:
                    method = msg["method"]
                    params = msg.get("params", {})
                    if method == "Runtime.consoleAPICalled":
                        msg_type = params.get("type")
                        text = " ".join(str(arg.get("value", "")) for arg in params.get("args", []))
                        self.console_messages.append({"type": msg_type, "text": text})
                        if msg_type in ["error", "assert"]:
                            self.console_errors.append({"type": msg_type, "text": text})
                    elif method == "Runtime.exceptionThrown":
                        details = params.get("exceptionDetails", {})
                        self.exceptions.append(details)
                    elif method == "Network.loadingFailed":
                        url = params.get("url", "")
                        canceled = params.get("canceled", False)
                        if not canceled and not url.endswith("favicon.ico"):
                            self.network_failures.append(params)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def send(self, method, params=None, timeout=15.0):
        self.msg_id += 1
        call_id = self.msg_id
        payload = {"id": call_id, "method": method}
        if params is not None:
            payload["params"] = params

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.pending_responses[call_id] = future

        await self.ws.send(json.dumps(payload))
        return await asyncio.wait_for(future, timeout=timeout)

    async def eval_js(self, expression, timeout=15.0):
        res = await self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True
            },
            timeout=timeout
        )
        result_obj = res.get("result", {}).get("result", {})
        if "value" in result_obj:
            return result_obj["value"]
        if result_obj.get("type") == "undefined":
            return None
        return result_obj

    async def close(self):
        self.is_running = False
        if self.listener_task:
            self.listener_task.cancel()
        if self.ws:
            await self.ws.close()


class TestInteractiveDeliverable(unittest.TestCase):
    edge_process = None
    user_data_dir = None
    cdp = None
    loop = None

    @classmethod
    def setUpClass(cls):
        if not HTML_PATH.exists():
            raise FileNotFoundError(f"Cannot find {HTML_PATH}")

        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)

        cls.user_data_dir = tempfile.mkdtemp()

        # Launch Edge in isolated headless mode
        cls.edge_process = subprocess.Popen([
            EDGE_EXE,
            "--headless=new",
            f"--user-data-dir={cls.user_data_dir}",
            "--remote-debugging-port=9222",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-gpu",
            "about:blank"
        ])

        # Poll until Edge debug port responds and find page target
        ws_url = None
        for _ in range(40):
            try:
                with urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=1.0) as resp:
                    targets = json.loads(resp.read().decode())
                    for t in targets:
                        if t.get("type") == "page":
                            ws_url = t.get("webSocketDebuggerUrl")
                            break
                    if ws_url:
                        break
            except Exception:
                time.sleep(0.2)

        if not ws_url:
            cls.edge_process.terminate()
            raise RuntimeError("Failed to obtain Page WebSocket Debugger URL from Edge")

        cls.cdp = CDPClient(ws_url)
        cls.loop.run_until_complete(cls._init_browser())

    @classmethod
    async def _init_browser(cls):
        await cls.cdp.connect()
        await cls.cdp.send("Page.enable")
        await cls.cdp.send("Runtime.enable")
        await cls.cdp.send("Network.enable")
        await cls.cdp.send("Log.enable")

        file_url = HTML_PATH.resolve().as_uri()
        await cls.cdp.send("Page.navigate", {"url": file_url})
        # Allow DOMContentLoaded and external CDN scripts (Tailwind, Chart.js) to load
        await asyncio.sleep(3.0)

    @classmethod
    def tearDownClass(cls):
        if cls.cdp and cls.loop:
            cls.loop.run_until_complete(cls.cdp.close())
        if cls.edge_process:
            cls.edge_process.terminate()
            cls.edge_process.wait()
        if cls.user_data_dir:
            shutil.rmtree(cls.user_data_dir, ignore_errors=True)
        if cls.loop:
            cls.loop.close()

    def run_async(self, coro):
        return self.loop.run_until_complete(coro)

    def test_01_standalone_and_initial_load(self):
        """Verify standalone file:/// operation, exactly 100 rows rendered, and initial counter."""
        row_count = self.run_async(self.cdp.eval_js(
            "document.querySelectorAll('#appsTableBody tr').length"
        ))
        self.assertEqual(row_count, 100, "Initial table must render exactly 100 application rows")

        counter_text = self.run_async(self.cdp.eval_js(
            "document.getElementById('tableRowCounter').innerText.trim()"
        ))
        self.assertEqual(counter_text, "Showing 100 of 100 apps")

        first_app_id = self.run_async(self.cdp.eval_js(
            "document.querySelector('#appsTableBody tr:first-child td:first-child').innerText.trim()"
        ))
        self.assertEqual(first_app_id, "1")

        first_app_name = self.run_async(self.cdp.eval_js(
            "document.querySelector('#appsTableBody tr:first-child td:nth-child(2)').innerText"
        ))
        self.assertIn("Salesforce", first_app_name)

        last_app_id = self.run_async(self.cdp.eval_js(
            "document.querySelector('#appsTableBody tr:last-child td:first-child').innerText.trim()"
        ))
        self.assertEqual(last_app_id, "100")

    def test_02_search_filtering(self):
        """Verify real-time name search filtering and row counter updates."""
        # Test 1: Search 'slack'
        res = self.run_async(self.cdp.eval_js("""
            (() => {
                const input = document.getElementById('searchInput');
                input.value = 'slack';
                input.dispatchEvent(new Event('input'));
                const rows = document.querySelectorAll('#appsTableBody tr');
                const counter = document.getElementById('tableRowCounter').innerText.trim();
                const appName = rows.length > 0 ? rows[0].querySelector('td:nth-child(2)').innerText : '';
                return { count: rows.length, counter, appName };
            })()
        """))
        self.assertEqual(res["count"], 1)
        self.assertIn("Slack", res["appName"])
        self.assertEqual(res["counter"], "Showing 1 of 100 apps")

        # Test 2: Search 'salesforce' (should match 'Salesforce' and 'Salesforce Commerce Cloud')
        res_sf = self.run_async(self.cdp.eval_js("""
            (() => {
                const input = document.getElementById('searchInput');
                input.value = 'salesforce';
                input.dispatchEvent(new Event('input'));
                const rows = document.querySelectorAll('#appsTableBody tr');
                const counter = document.getElementById('tableRowCounter').innerText.trim();
                const names = Array.from(rows).map(r => r.querySelector('td:nth-child(2)').innerText);
                return { count: rows.length, counter, names };
            })()
        """))
        self.assertEqual(res_sf["count"], 2)
        self.assertEqual(res_sf["counter"], "Showing 2 of 100 apps")
        self.assertTrue(any("Salesforce Commerce Cloud" in n for n in res_sf["names"]))

        # Test 3: Search 'notion'
        res_notion = self.run_async(self.cdp.eval_js("""
            (() => {
                const input = document.getElementById('searchInput');
                input.value = 'notion';
                input.dispatchEvent(new Event('input'));
                const rows = document.querySelectorAll('#appsTableBody tr');
                const counter = document.getElementById('tableRowCounter').innerText.trim();
                return { count: rows.length, counter };
            })()
        """))
        self.assertEqual(res_notion["count"], 1)
        self.assertEqual(res_notion["counter"], "Showing 1 of 100 apps")

        # Test 4: Clear search
        res_clear = self.run_async(self.cdp.eval_js("""
            (() => {
                const input = document.getElementById('searchInput');
                input.value = '';
                input.dispatchEvent(new Event('input'));
                const rows = document.querySelectorAll('#appsTableBody tr');
                const counter = document.getElementById('tableRowCounter').innerText.trim();
                return { count: rows.length, counter };
            })()
        """))
        self.assertEqual(res_clear["count"], 100)
        self.assertEqual(res_clear["counter"], "Showing 100 of 100 apps")

    def test_03_category_filtering(self):
        """Verify category dropdown filtering across all 10 categories."""
        categories = [
            "CRM and Sales",
            "Support and Helpdesk",
            "Communications and Messaging",
            "Marketing, Ads, Email and Social",
            "Ecommerce",
            "Data, SEO and Scraping",
            "Developer, Infra and Data Platforms",
            "Productivity and Project Management",
            "Finance and Fintech",
            "AI, Research and Media-native"
        ]

        for cat in categories:
            res = self.run_async(self.cdp.eval_js(f"""
                (() => {{
                    const sel = document.getElementById('categoryFilter');
                    sel.value = '{cat}';
                    sel.dispatchEvent(new Event('change'));
                    const rows = document.querySelectorAll('#appsTableBody tr');
                    const counter = document.getElementById('tableRowCounter').innerText.trim();
                    const allMatch = Array.from(rows).every(r => r.querySelector('td:nth-child(3)').innerText.trim() === '{cat}');
                    return {{ count: rows.length, counter, allMatch }};
                }})()
            """))
            self.assertEqual(res["count"], 10, f"Category '{cat}' should render exactly 10 rows")
            self.assertEqual(res["counter"], "Showing 10 of 100 apps")
            self.assertTrue(res["allMatch"], f"All rows must have category '{cat}'")

        # Reset category filter
        reset_res = self.run_async(self.cdp.eval_js("""
            (() => {
                const sel = document.getElementById('categoryFilter');
                sel.value = '';
                sel.dispatchEvent(new Event('change'));
                const rows = document.querySelectorAll('#appsTableBody tr');
                return { count: rows.length };
            })()
        """))
        self.assertEqual(reset_res["count"], 100)

    def test_04_verdict_filtering(self):
        """Verify verdict (buildability) dropdown filtering across all statuses."""
        verdict_counts = {
            "build-today": 83,
            "build-after-outreach": 12,
            "not-buildable": 3,
            "build-paid": 1,
            "needs-research": 1
        }

        for verdict, expected_count in verdict_counts.items():
            res = self.run_async(self.cdp.eval_js(f"""
                (() => {{
                    const sel = document.getElementById('verdictFilter');
                    sel.value = '{verdict}';
                    sel.dispatchEvent(new Event('change'));
                    const rows = document.querySelectorAll('#appsTableBody tr');
                    const counter = document.getElementById('tableRowCounter').innerText.trim();
                    const allMatch = Array.from(rows).every(r => r.querySelector('td:nth-child(9)').innerText.includes('{verdict}'));
                    return {{ count: rows.length, counter, allMatch }};
                }})()
            """))
            self.assertEqual(res["count"], expected_count, f"Verdict '{verdict}' should render {expected_count} rows")
            self.assertEqual(res["counter"], f"Showing {expected_count} of 100 apps")
            self.assertTrue(res["allMatch"], f"All rows must have verdict badge '{verdict}'")

        # Reset verdict filter
        reset_res = self.run_async(self.cdp.eval_js("""
            (() => {
                const sel = document.getElementById('verdictFilter');
                sel.value = '';
                sel.dispatchEvent(new Event('change'));
                return document.querySelectorAll('#appsTableBody tr').length;
            })()
        """))
        self.assertEqual(reset_res, 100)

    def test_05_combined_filtering(self):
        """Verify compound filtering with search + category + verdict."""
        # Search 'sales' + category 'CRM and Sales' + verdict 'build-today' -> 1 app (Salesforce)
        res = self.run_async(self.cdp.eval_js("""
            (() => {
                const search = document.getElementById('searchInput');
                const cat = document.getElementById('categoryFilter');
                const verd = document.getElementById('verdictFilter');

                search.value = 'sales';
                cat.value = 'CRM and Sales';
                verd.value = 'build-today';
                search.dispatchEvent(new Event('input'));

                const rows = document.querySelectorAll('#appsTableBody tr');
                const counter = document.getElementById('tableRowCounter').innerText.trim();
                const name = rows.length > 0 ? rows[0].querySelector('td:nth-child(2)').innerText : '';
                return { count: rows.length, counter, name };
            })()
        """))
        self.assertEqual(res["count"], 1)
        self.assertIn("Salesforce", res["name"])
        self.assertEqual(res["counter"], "Showing 1 of 100 apps")

        # Nonexistent search term -> 0 apps
        res_zero = self.run_async(self.cdp.eval_js("""
            (() => {
                const search = document.getElementById('searchInput');
                search.value = 'nonexistentxyzterm';
                search.dispatchEvent(new Event('input'));
                const rows = document.querySelectorAll('#appsTableBody tr');
                const counter = document.getElementById('tableRowCounter').innerText.trim();
                return { count: rows.length, counter };
            })()
        """))
        self.assertEqual(res_zero["count"], 0)
        self.assertEqual(res_zero["counter"], "Showing 0 of 100 apps")

        # Reset all filters
        res_reset = self.run_async(self.cdp.eval_js("""
            (() => {
                document.getElementById('searchInput').value = '';
                document.getElementById('categoryFilter').value = '';
                document.getElementById('verdictFilter').value = '';
                document.getElementById('searchInput').dispatchEvent(new Event('input'));
                return document.querySelectorAll('#appsTableBody tr').length;
            })()
        """))
        self.assertEqual(res_reset, 100)

    def test_06_column_header_sorting(self):
        """Verify column sorting for numeric (id), alphabetical (name), and boolean (has_mcp)."""
        # Sort by Name ASC & DESC
        names_asc = self.run_async(self.cdp.eval_js("""
            (() => {
                sortTable('name');
                const rows = document.querySelectorAll('#appsTableBody tr');
                const first = rows[0].querySelector('td:nth-child(2)').innerText.trim();
                const last = rows[rows.length - 1].querySelector('td:nth-child(2)').innerText.trim();
                return { first, last };
            })()
        """))
        self.assertTrue(names_asc["first"].startswith("Ahrefs"), f"Expected Ahrefs first, got {names_asc['first']}")
        self.assertTrue(names_asc["last"].startswith("Zoho CRM"), f"Expected Zoho CRM last, got {names_asc['last']}")

        names_desc = self.run_async(self.cdp.eval_js("""
            (() => {
                sortTable('name');
                const rows = document.querySelectorAll('#appsTableBody tr');
                const first = rows[0].querySelector('td:nth-child(2)').innerText.trim();
                const last = rows[rows.length - 1].querySelector('td:nth-child(2)').innerText.trim();
                return { first, last };
            })()
        """))
        self.assertTrue(names_desc["first"].startswith("Zoho CRM"), f"Expected Zoho CRM first in DESC, got {names_desc['first']}")
        self.assertTrue(names_desc["last"].startswith("Ahrefs"), f"Expected Ahrefs last in DESC, got {names_desc['last']}")

        # Sort by ID ASC & DESC
        id_sort = self.run_async(self.cdp.eval_js("""
            (() => {
                sortTable('id');
                const rows = document.querySelectorAll('#appsTableBody tr');
                const first = parseInt(rows[0].querySelector('td:first-child').innerText.trim());
                const last = parseInt(rows[rows.length - 1].querySelector('td:first-child').innerText.trim());
                return { first, last };
            })()
        """))
        self.assertEqual(id_sort["first"], 1)
        self.assertEqual(id_sort["last"], 100)

        id_sort_desc = self.run_async(self.cdp.eval_js("""
            (() => {
                sortTable('id');
                const rows = document.querySelectorAll('#appsTableBody tr');
                const first = parseInt(rows[0].querySelector('td:first-child').innerText.trim());
                const last = parseInt(rows[rows.length - 1].querySelector('td:first-child').innerText.trim());
                return { first, last };
            })()
        """))
        self.assertEqual(id_sort_desc["first"], 100)
        self.assertEqual(id_sort_desc["last"], 1)

        # Sort by has_mcp (boolean)
        mcp_asc = self.run_async(self.cdp.eval_js("""
            (() => {
                sortTable('has_mcp');
                const rows = document.querySelectorAll('#appsTableBody tr');
                const first = rows[0].querySelector('td:nth-child(8)').innerText.trim();
                const last = rows[rows.length - 1].querySelector('td:nth-child(8)').innerText.trim();
                return { first, last };
            })()
        """))
        self.assertEqual(mcp_asc["first"], "—")
        self.assertEqual(mcp_asc["last"], "✓")

        # Reset back to ID ASC
        self.run_async(self.cdp.eval_js("""
            (() => {
                sortTable('id');
                if (parseInt(document.querySelector('#appsTableBody tr:first-child td:first-child').innerText.trim()) !== 1) {
                    sortTable('id');
                }
            })()
        """))

    def test_07_chart_js_visualizations(self):
        """Verify all 4 Chart.js charts initialize, have bounding dimensions, and non-zero dataset values."""
        charts_info = self.run_async(self.cdp.eval_js("""
            (() => {
                const charts = ['authDonutChart', 'buildabilityBarChart', 'accessCategoryChart', 'selfServeRateChart'];
                const info = {};
                for (const id of charts) {
                    const canvas = document.getElementById(id);
                    const chart = window.Chart ? Chart.getChart(id) : null;
                    const rect = canvas ? canvas.getBoundingClientRect() : { width: 0, height: 0 };
                    info[id] = {
                        exists: !!chart,
                        type: chart ? chart.config.type : null,
                        labelsCount: chart && chart.data && chart.data.labels ? chart.data.labels.length : 0,
                        datasetsCount: chart && chart.data && chart.data.datasets ? chart.data.datasets.length : 0,
                        width: rect.width,
                        height: rect.height,
                        hasNonZeroData: chart && chart.data && chart.data.datasets ? chart.data.datasets.some(d => d.data && d.data.some(v => v > 0)) : false
                    };
                }
                return info;
            })()
        """))

        for chart_id in ['authDonutChart', 'buildabilityBarChart', 'accessCategoryChart', 'selfServeRateChart']:
            self.assertIn(chart_id, charts_info, f"Missing chart info for {chart_id}")
            data = charts_info[chart_id]
            self.assertTrue(data["exists"], f"Chart {chart_id} failed to initialize with Chart.js")
            self.assertGreater(data["width"], 100, f"Chart {chart_id} canvas has zero or trivial width")
            self.assertGreater(data["height"], 100, f"Chart {chart_id} canvas has zero or trivial height")
            self.assertGreater(data["labelsCount"], 0, f"Chart {chart_id} has 0 labels")
            self.assertGreater(data["datasetsCount"], 0, f"Chart {chart_id} has 0 datasets")
            self.assertTrue(data["hasNonZeroData"], f"Chart {chart_id} has all zero or empty dataset values")

        # Specific Chart 1 checks:
        self.assertEqual(charts_info['authDonutChart']['type'], 'doughnut')
        self.assertEqual(charts_info['authDonutChart']['labelsCount'], 4)

        # Specific Chart 2 checks:
        self.assertEqual(charts_info['buildabilityBarChart']['type'], 'bar')
        self.assertEqual(charts_info['buildabilityBarChart']['labelsCount'], 5)

        # Specific Chart 3 checks (6 access models x 10 categories):
        self.assertEqual(charts_info['accessCategoryChart']['type'], 'bar')
        self.assertEqual(charts_info['accessCategoryChart']['labelsCount'], 10)
        self.assertEqual(charts_info['accessCategoryChart']['datasetsCount'], 6)

        # Specific Chart 4 checks:
        self.assertEqual(charts_info['selfServeRateChart']['type'], 'bar')
        self.assertEqual(charts_info['selfServeRateChart']['labelsCount'], 10)

    def test_08_section_f_human_verification_table(self):
        """Verify Section F human verification audit table renders 20 apps with correct badges and notes."""
        res = self.run_async(self.cdp.eval_js("""
            (() => {
                const rows = document.querySelectorAll('#verifiedTableBody tr');
                const apps = Array.from(rows).map(r => {
                    const tds = r.querySelectorAll('td');
                    return {
                        id: parseInt(tds[0].innerText.trim()),
                        name: tds[1].innerText.trim(),
                        category: tds[2].innerText.trim(),
                        verdict: tds[3].innerText.trim(),
                        notes: tds[4].innerText.trim()
                    };
                });
                return { count: rows.length, apps };
            })()
        """))

        self.assertEqual(res["count"], 20, "Section F table must render exactly 20 audited apps")
        apps = res["apps"]

        # Check category distribution (2 per category across 10 categories)
        categories = set(a["category"] for a in apps)
        self.assertEqual(len(categories), 10, "Section F must cover all 10 categories")
        for cat in categories:
            cat_apps = [a for a in apps if a["category"] == cat]
            self.assertEqual(len(cat_apps), 2, f"Category '{cat}' must have exactly 2 verified apps in Section F")

        # Check verdict distribution
        verdicts = [a["verdict"] for a in apps]
        self.assertEqual(verdicts.count("CORRECT"), 14, "Section F must contain 14 CORRECT badges")
        self.assertEqual(verdicts.count("PARTIALLY-CORRECT"), 2, "Section F must contain 2 PARTIALLY-CORRECT badges")
        self.assertEqual(verdicts.count("WRONG"), 4, "Section F must contain 4 WRONG badges")

        # Check notes present on all 20 rows
        for a in apps:
            self.assertGreater(len(a["notes"]), 5, f"App {a['name']} missing audit notes in Section F")

        # Verify key corrected apps
        app_51 = next(a for a in apps if a["id"] == 51)
        self.assertEqual(app_51["name"], "DataForSEO")
        self.assertEqual(app_51["verdict"], "WRONG")
        self.assertIn("Basic Auth", app_51["notes"])

        app_14 = next(a for a in apps if a["id"] == 14)
        self.assertEqual(app_14["name"], "Front")
        self.assertEqual(app_14["verdict"], "WRONG")
        self.assertIn("build-paid", app_14["notes"])

        app_44 = next(a for a in apps if a["id"] == 44)
        self.assertEqual(app_44["name"], "Salesforce Commerce Cloud")
        self.assertEqual(app_44["verdict"], "WRONG")
        self.assertIn("contact-sales", app_44["notes"])

    def test_09_browser_console_and_network_errors(self):
        """Verify zero JavaScript errors, zero uncaught exceptions, and zero network resource errors."""
        console_errors = self.cdp.console_errors
        exceptions = self.cdp.exceptions
        network_failures = self.cdp.network_failures

        self.assertEqual(len(console_errors), 0, f"Encountered browser console errors: {console_errors}")
        self.assertEqual(len(exceptions), 0, f"Encountered uncaught JavaScript exceptions: {exceptions}")
        self.assertEqual(len(network_failures), 0, f"Encountered failed network requests: {network_failures}")


if __name__ == "__main__":
    unittest.main()
