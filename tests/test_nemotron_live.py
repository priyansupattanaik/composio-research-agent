import json
import os
import unittest

from dotenv import load_dotenv

from agent.extractor import clean_json_response, extract_app_record, nvidia_api_key

load_dotenv()


@unittest.skipUnless(bool(nvidia_api_key()), "NVIDIA_API_KEY not configured")
class TestNemotronLiveExtraction(unittest.TestCase):
    def test_live_json_extraction_for_self_serve_rest_app(self):
        record = extract_app_record(
            {
                "id": 21,
                "name": "Slack",
                "category": "Communications and Messaging",
                "hint_url": "api.slack.com",
            },
            "Slack Web API uses OAuth 2.0. Create an app at api.slack.com and install it to a workspace to receive a bot token. REST methods are documented at api.slack.com/methods.",
            "Create a Slack app. OAuth 2.0. Bot tokens. REST API. Sign up at api.slack.com. Developer dashboard generates tokens immediately.",
            "https://api.slack.com",
        )
        self.assertEqual(record["name"], "Slack")
        self.assertIn(record["primary_auth"], ["OAuth2", "API Key", "Bearer Token"])
        self.assertEqual(record["access_model"], "self-serve")
        self.assertIn(record["api_type"], ["REST", "REST+GraphQL", "WebSocket"])
        self.assertEqual(record["buildability"], "build-today")
        self.assertTrue(str(record["evidence_url"]).startswith("http"))

    def test_clean_json_response_roundtrip(self):
        payload = {"buildability": "build-today", "access_model": "self-serve"}
        raw = "<think>x</think>```json\n" + json.dumps(payload) + "\n```"
        self.assertEqual(json.loads(clean_json_response(raw)), payload)


if __name__ == "__main__":
    unittest.main()
