import json
import os
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from app.llm.errors import AnalysisError
from app.llm.snowchat import SnowChatProvider
from app.pipeline import analyze, gap_stage
from app.schemas import Requirement
from app.schemas import ExtractionOutput, GapOutput


class SnowChatTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"FACTCHAT_API_KEY": "test-only", "LLM_PROVIDER": "snowchat"}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_two_stages_use_schemas_original_text_and_usage(self):
        provider = SnowChatProvider()
        calls = []

        def request(path, body=None):
            if path.startswith("/models/"):
                return {"data": [{"id": "gpt-5.6-luna", "type": "llm"}]}
            calls.append(body)
            payload = json.loads(body["messages"][1]["content"])
            if len(calls) == 1:
                output = {"requirements": [{"project_id": payload["project_id"], "id": "REQ-1",
                    "category": "functional", "description": "사용자는 예약할 수 있다.",
                    "status": "confirmed", "source": "initial_input", "blocking": False, "acceptance_criteria": []}]}
            else:
                self.assertEqual(payload["text"], "사용자는 예약할 수 있다.")
                self.assertEqual(payload["requirements"][0]["id"], "REQ-1")
                output = {"gaps": [{"id": "GAP-1", "category": "modify_cancel", "description": "취소 정책 미정",
                                    "blocking": True, "related_requirement_ids": ["REQ-1"]}]}
            return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output)}}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 8}}

        with patch.object(provider, "request", side_effect=request):
            result = analyze("사용자는 예약할 수 있다.", provider)
        self.assertEqual(result.analysis_mode, "snowchat")
        self.assertTrue(result.clarification_needed)
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0]["messages"][0], calls[1]["messages"][0])
        self.assertEqual([c["model"] for c in calls], ["gpt-5.6-luna"] * 2)
        self.assertEqual([r["input_tokens"] for r in result.usage], [12, 12])
        self.assertTrue(all(r["success"] for r in result.usage))
        for body in calls:
            self.assertTrue(body["response_format"]["json_schema"]["strict"])

    def test_schemas_forbid_extra_fields_and_require_all_properties(self):
        def check(node):
            if isinstance(node, dict):
                if node.get("type") == "object":
                    self.assertIs(node.get("additionalProperties"), False)
                    self.assertEqual(set(node["required"]), set(node["properties"]))
                for value in node.values():
                    check(value)
            elif isinstance(node, list):
                for value in node:
                    check(value)
        for output_type in [ExtractionOutput, GapOutput]:
            check(output_type.model_json_schema())

    def test_missing_luna_never_falls_back_to_terra(self):
        provider = SnowChatProvider()
        provider.models = ["gpt-5.6-terra"]
        with self.assertRaises(AnalysisError) as error:
            provider.model_for("requirement_extraction")
        self.assertEqual(error.exception.code, "model_unavailable")

    def test_explicit_stage_model_is_checked_against_list(self):
        provider = SnowChatProvider()
        provider.models = ["account-model"]
        with patch.dict(os.environ, {"SNOWCHAT_GAP_MODEL": "account-model"}):
            self.assertEqual(provider.model_for("gap_analysis"), "account-model")

    def test_missing_key_and_http_errors(self):
        with patch.dict(os.environ, {"FACTCHAT_API_KEY": ""}):
            with self.assertRaises(AnalysisError) as error:
                SnowChatProvider()
            self.assertEqual(error.exception.code, "missing_api_key")
        provider = SnowChatProvider()
        for status, code in [(401, "authentication_failed"), (403, "model_unavailable"),
                             (429, "rate_limit"), (500, "gateway_error"), (400, "request_rejected")]:
            with self.subTest(status=status), patch.object(provider.opener, "open", side_effect=HTTPError("url", status, "secret-error", {}, BytesIO(b"secret"))):
                with self.assertRaises(AnalysisError) as error:
                    provider.list_models()
                self.assertEqual(error.exception.code, code)
                self.assertNotIn("secret", str(error.exception))
        with patch.object(provider.opener, "open", side_effect=TimeoutError):
            with self.assertRaises(AnalysisError) as error:
                provider.list_models()
            self.assertEqual(error.exception.code, "timeout")

    def test_empty_response(self):
        with self.assertRaises(AnalysisError) as error:
            SnowChatProvider.content({"choices": [{"finish_reason": "stop", "message": {"content": ""}}]})
        self.assertEqual(error.exception.code, "empty_response")

    def test_invalid_output_stops_before_gap_stage_without_fallback(self):
        provider = SnowChatProvider()
        provider.models = ["gpt-5.6-luna"]
        with patch.object(provider, "complete", return_value=('{"requirements":[{"description":"bad"}]}', None)) as complete:
            with self.assertRaises(AnalysisError) as error:
                analyze("input", provider)
            self.assertEqual(error.exception.code, "structured_output_invalid")
            self.assertEqual(complete.call_count, 1)

    def test_unknown_requirement_reference_is_rejected(self):
        provider = SnowChatProvider()
        provider.models = ["gpt-5.6-luna"]
        gap = {"gaps": [{"id": "G-1", "category": "core_flow", "description": "unknown", "blocking": True, "related_requirement_ids": ["missing"]}]}
        with patch.object(provider, "complete", side_effect=[('{"requirements":[]}', None), (json.dumps(gap), None)]):
            with self.assertRaises(AnalysisError) as error:
                analyze("input", provider)
            self.assertEqual(error.exception.code, "structured_output_invalid")

    def test_blocking_requirement_cannot_disappear_from_gaps(self):
        provider = SnowChatProvider()
        provider.models = ["gpt-5.6-luna"]
        requirement = Requirement(project_id="p", id="REQ-1", category="permission",
                                  description="승인자는 미정", status="needs_clarification",
                                  source="initial_input", blocking=True)
        with patch.object(provider, "complete", return_value=('{"gaps":[]}', None)):
            with self.assertRaises(AnalysisError) as error:
                gap_stage(provider, "승인자는 미정", [requirement], "run", [])
            self.assertEqual(error.exception.code, "structured_output_invalid")


if __name__ == "__main__":
    unittest.main()
