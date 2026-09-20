import json
import os
import unittest
from unittest.mock import MagicMock, patch

from agent.extractor import (
    call_nvidia_nemotron,
    clean_json_response,
    derive_buildability,
    extract_app_record,
    fallback_heuristic_extraction,
    infer_access_model,
)


MAILCHIMP_PAGE = """
Build with Mailchimp
Mailchimp Marketing API
Send marketing campaigns
Mailchimp Transactional
You'll be in good company
Mailchimp integration partner program
A helping hand to scale your Mailchimp integration
As an integration partner, you'll have access to exclusive benefits
Create an API key in your account settings
OAuth 2.0 is supported
REST API
Sign up for a free developer account
"""

ASANA_PAGE = """
For developers and teams
Publish your app in our directory of 200+ partners
The Asana partners program provides technology companies with a platform
REST API authentication with personal access tokens
Create a developer account and generate a token
OAuth 2.0
"""

RAMP_PAGE = """
Build once. Automate forever.
Join the technology partner program.
Ramp developer API
Create an API key from the Ramp developer dashboard
OAuth 2.0
REST
"""

TRUE_PARTNER_GATE = """
The vendor API is partner-only.
API access is only available to approved partners.
You must become an approved partner to access the API.
REST endpoints require partner approval for API credentials.
"""


class TestAccessModelHeuristic(unittest.TestCase):
    def test_partner_program_marketing_is_not_an_api_gate(self):
        self.assertEqual(infer_access_model(MAILCHIMP_PAGE), "self-serve")
        self.assertEqual(infer_access_model(ASANA_PAGE), "self-serve")
        self.assertEqual(infer_access_model(RAMP_PAGE), "self-serve")

    def test_true_partner_gate_still_detected(self):
        self.assertEqual(infer_access_model(TRUE_PARTNER_GATE), "partner-gated")

    def test_mailchimp_like_corpus_is_build_today(self):
        record = fallback_heuristic_extraction(
            {"id": 35, "name": "Mailchimp", "category": "Marketing, Ads, Email and Social"},
            "Mailchimp Marketing API OAuth 2.0 REST",
            MAILCHIMP_PAGE,
            "https://mailchimp.com/developer/",
        )
        self.assertEqual(record["access_model"], "self-serve")
        self.assertEqual(record["buildability"], "build-today")
        self.assertIsNone(record["main_blocker"])

    def test_asana_like_corpus_is_build_today(self):
        record = fallback_heuristic_extraction(
            {"id": 75, "name": "Asana", "category": "Productivity and Project Management"},
            "Asana REST API personal access token OAuth",
            ASANA_PAGE,
            "https://developers.asana.com/docs",
        )
        self.assertEqual(record["access_model"], "self-serve")
        self.assertEqual(record["buildability"], "build-today")


class TestDeriveBuildability(unittest.TestCase):
    def test_self_serve_rest_is_build_today(self):
        verdict, blocker = derive_buildability("self-serve", "REST")
        self.assertEqual(verdict, "build-today")
        self.assertIsNone(blocker)

    def test_no_public_api_is_not_buildable(self):
        verdict, blocker = derive_buildability("no-public-api", "No Public API")
        self.assertEqual(verdict, "not-buildable")
        self.assertIsNotNone(blocker)

    def test_contact_sales_cannot_be_build_today(self):
        verdict, blocker = derive_buildability("contact-sales", "REST")
        self.assertEqual(verdict, "build-after-outreach")
        self.assertIsNotNone(blocker)


class TestNemotronProvider(unittest.TestCase):
    def test_clean_json_strips_think_tags_and_fences(self):
        raw = "<think>reasoning</think>\n```json\n{\"buildability\": \"build-today\"}\n```"
        cleaned = clean_json_response(raw)
        self.assertEqual(json.loads(cleaned)["buildability"], "build-today")

    @patch("agent.extractor.call_nvidia_nemotron")
    @patch("agent.extractor.call_anthropic")
    @patch("agent.extractor.call_openai")
    def test_extract_prefers_nvidia_nemotron(self, mock_openai, mock_anthropic, mock_nvidia):
        mock_nvidia.return_value = json.dumps({
            "id": 21,
            "name": "Slack",
            "category": "Communications and Messaging",
            "one_liner": "Team chat API",
            "auth_methods": ["OAuth2"],
            "primary_auth": "OAuth2",
            "auth_notes": "OAuth2 bot tokens",
            "access_model": "self-serve",
            "access_notes": "Create an app at api.slack.com",
            "api_type": "REST",
            "api_breadth": "large",
            "has_mcp": False,
            "mcp_url": None,
            "buildability": "build-today",
            "main_blocker": None,
            "evidence_url": "https://api.slack.com",
            "confidence": "high",
            "agent_notes": "Nemotron extraction",
        })
        with patch.dict(os.environ, {"NVIDIA_API_KEY": "nvapi-test-key"}, clear=False):
            record = extract_app_record(
                {"id": 21, "name": "Slack", "category": "Communications and Messaging", "hint_url": "api.slack.com"},
                "Slack OAuth2 REST API",
                "Create an app and generate a bot token. OAuth 2.0.",
                "https://api.slack.com",
            )
        self.assertEqual(record["buildability"], "build-today")
        mock_nvidia.assert_called_once()
        mock_anthropic.assert_not_called()
        mock_openai.assert_not_called()

    @patch("openai.OpenAI")
    def test_call_nvidia_nemotron_uses_nim_base_url(self, mock_openai_cls):
        client = MagicMock()
        mock_openai_cls.return_value = client
        client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content='{"ok": true}'))
        ]
        with patch.dict(
            os.environ,
            {
                "NVIDIA_API_KEY": "nvapi-test-key",
                "NVIDIA_MODEL": "nvidia/nemotron-3.5-lightning-30b-a3b",
                "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1",
            },
            clear=False,
        ):
            text = call_nvidia_nemotron("return json")
        self.assertEqual(text, '{"ok": true}')
        mock_openai_cls.assert_called_with(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key="nvapi-test-key",
        )
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "nvidia/nemotron-3.5-lightning-30b-a3b")


if __name__ == "__main__":
    unittest.main()
