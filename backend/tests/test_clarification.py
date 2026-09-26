import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app.llm.errors import AnalysisError
from app.llm.mock import MockProvider, analyze_gaps
from app.llm.snowchat import SnowChatProvider
from app.pipeline import question_stage, update_stage
from app.schemas import (
    Answer, ClarificationQuestion, Gap, QuestionOutput, Requirement, RequirementUpdateOutput,
)

HANDOFF = json.loads(
    (Path(__file__).resolve().parents[2] / "docs/examples/snowchat-handoff.json").read_text(encoding="utf-8"))
PID = HANDOFF["project_id"]
TEXT = "직원들이 휴가를 신청하고 관리자가 승인할 수 있는 사내 휴가관리 서비스를 만들어줘."
REQS = [Requirement.model_validate(r) for r in HANDOFF["requirements"]]
GAPS = [Gap.model_validate(g) for g in HANDOFF["gaps"]]


class StubProvider:
    """Returns a fixed JSON output, to exercise run_stage validation only."""
    mode = "mock"

    def __init__(self, output):
        self.output = output

    def model_for(self, stage):
        return None

    def complete(self, stage, prompt, payload, output_type, model):
        return json.dumps(self.output), None


def question(gap_id, text="어떻게 하나요?", proposal="기본값을 적용한다."):
    return {"gap_id": gap_id, "question": text, "ai_proposal": proposal}


def updated(id, **changes):
    return {"project_id": PID, "id": id, "category": "business_rule", "description": "답변 내용",
            "status": "confirmed", "source": "clarification_answer", "blocking": False,
            "acceptance_criteria": [], **changes}


def ask(provider, reqs=REQS, gaps=GAPS, records=None):
    return question_stage(provider, TEXT, reqs, gaps, PID, "run", [] if records is None else records)


def update(provider, reqs=REQS, answers=None, records=None):
    questions = [ClarificationQuestion(**question(g.id)) for g in GAPS]
    answers = answers if answers is not None else [Answer(gap_id="GAP-005", answer="승인 전까지 직원이 취소할 수 있다.")]
    return update_stage(provider, TEXT, reqs, GAPS, questions, answers, PID, "run",
                        [] if records is None else records)


class QuestionStageTest(unittest.TestCase):
    def test_rejects_invalid_question_output(self):
        all_ids = [g.id for g in GAPS]
        cases = {
            "missing blocking gap": [question(i) for i in all_ids[:-1]],
            "unknown gap": [question(i) for i in all_ids] + [question("GAP-999")],
            "duplicate": [question(i) for i in all_ids] + [question(all_ids[0])],
            "empty question": [question(i) for i in all_ids[:-1]] + [question(all_ids[-1], text=" ")],
            "empty proposal": [question(i) for i in all_ids[:-1]] + [question(all_ids[-1], proposal="")],
        }
        for name, questions in cases.items():
            records = []
            with self.subTest(name), self.assertRaises(AnalysisError) as error:
                ask(StubProvider({"questions": questions}), records=records)
            self.assertEqual(error.exception.code, "structured_output_invalid")
            self.assertEqual(records[-1]["error"], "structured_output_invalid")

    def test_nonblocking_gap_gets_no_question(self):
        gaps = [*GAPS, Gap(id="GAP-006", related_requirement_ids=[], category="nfr", description="미정", blocking=False)]
        with self.assertRaises(AnalysisError):
            ask(StubProvider({"questions": [question(g.id) for g in gaps]}), gaps=gaps)
        self.assertEqual(len(ask(StubProvider({"questions": [question(g.id) for g in GAPS]}), gaps=gaps)), 5)


class UpdateStageTest(unittest.TestCase):
    def test_rejects_invalid_update_output(self):
        proposed = Requirement(project_id=PID, id="REQ-006", category="flow", description="AI 제안",
                               status="proposed", source="ai_proposal", blocking=False)
        cases = {
            "replaces proposed": ([*REQS, proposed], [updated("REQ-006")]),
            "replaces initial_input": (REQS, [updated("REQ-003")]),
            "wrong source": (REQS, [updated("REQ-006", source="ai_proposal")]),
            "proposed status": (REQS, [updated("REQ-006", status="proposed")]),
            "project mismatch": (REQS, [updated("REQ-006", project_id="other")]),
            "duplicate id": (REQS, [updated("REQ-006"), updated("REQ-006")]),
            "empty description": (REQS, [updated("REQ-006", description=" ")]),
        }
        for name, (reqs, output) in cases.items():
            with self.subTest(name), self.assertRaises(AnalysisError) as error:
                update(StubProvider({"requirements": output}), reqs=reqs)
            self.assertEqual(error.exception.code, "structured_output_invalid")

    def test_valid_update_returns_upserts(self):
        result = update(StubProvider({"requirements": [updated("REQ-006")]}))
        self.assertEqual([r.id for r in result], ["REQ-006"])


class MockClarificationTest(unittest.TestCase):
    def test_handoff_questions_and_keyword_answer_resolves_gap(self):
        records = []
        questions = ask(MockProvider(), records=records)
        self.assertEqual([q.gap_id for q in questions], [g.id for g in GAPS])
        self.assertTrue(all(q.question.strip() and q.ai_proposal.strip() for q in questions))
        answers = [Answer(gap_id="GAP-005", answer="승인 전까지 직원이 직접 할 수 있다."), Answer(gap_id="GAP-001", answer="")]
        result = update_stage(MockProvider(), TEXT, REQS, GAPS, questions, answers, PID, "run", records)
        self.assertEqual(len(result), 1)
        new = result[0]
        self.assertEqual((new.id, new.status, new.source, new.category), ("REQ-006", "confirmed", "clarification_answer", "business_rule"))
        self.assertTrue(new.description.startswith("승인 전까지 직원이 직접 할 수 있다."))
        self.assertEqual([r["stage"] for r in records], ["question_generation", "requirement_update"])

    def test_case_a_replaces_needs_clarification(self):
        reqs = [Requirement(project_id=PID, id="REQ-001", category="permission", description="승인자는 추후 결정",
                            status="needs_clarification", source="initial_input", blocking=True)]
        gaps = analyze_gaps(reqs)
        questions = ask(MockProvider(), reqs=reqs, gaps=gaps)
        answers = [Answer(gap_id=q.gap_id, answer="팀장이 승인한다.") for q in questions]
        result = update_stage(MockProvider(), TEXT, reqs, gaps, questions, answers, PID, "run", [])
        self.assertEqual([(r.id, r.status, r.blocking) for r in result], [("REQ-001", "confirmed", False)])
        self.assertFalse(any(g.blocking for g in analyze_gaps(result)))


class SnowChatClarificationTest(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"FACTCHAT_API_KEY": "test-only", "LLM_PROVIDER": "snowchat",
                                      "SNOWCHAT_GAP_MODEL": "gap-model", "SNOWCHAT_EXTRACTION_MODEL": "extract-model"},
                         clear=True)
        env.start()
        self.addCleanup(env.stop)

    def test_new_stages_send_strict_schema_with_gap_model(self):
        provider = SnowChatProvider()
        calls = []
        outputs = [{"questions": [question(g.id) for g in GAPS]}, {"requirements": [updated("REQ-006")]}]

        def request(path, body=None):
            if path.startswith("/models/"):
                return {"data": [{"id": "gap-model", "type": "llm"}, {"id": "extract-model", "type": "llm"}]}
            calls.append(body)
            return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(outputs[len(calls) - 1])}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

        records = []
        with patch.object(provider, "request", side_effect=request):
            ask(provider, records=records)
            update(provider, records=records)
        self.assertEqual([c["model"] for c in calls], ["gap-model", "gap-model"])
        self.assertEqual([c["response_format"]["json_schema"]["name"] for c in calls],
                         ["QuestionOutput", "RequirementUpdateOutput"])
        self.assertTrue(all(c["response_format"]["json_schema"]["strict"] for c in calls))
        update_payload = json.loads(calls[1]["messages"][1]["content"])
        self.assertEqual(update_payload["project_id"], PID)
        self.assertNotIn("ai_proposal", json.dumps(update_payload["clarifications"]))
        for record in records:
            self.assertEqual((record["project_id"], record["run_id"], record["cost"], record["input_tokens"]),
                             (PID, "run", None, 10))
            self.assertLessEqual(record["started_at"], record["ended_at"])

    def test_new_schemas_forbid_extra_fields_and_require_all_properties(self):
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
        for output_type in [QuestionOutput, RequirementUpdateOutput]:
            check(output_type.model_json_schema())


if __name__ == "__main__":
    unittest.main()
