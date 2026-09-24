import unittest

from pydantic import ValidationError

from app.pipeline import analyze as run_analysis
from app.llm.mock import MockProvider, analyze_gaps, extract_requirements
from app.schemas import Requirement

def analyze(text):
    return run_analysis(text, MockProvider())


class AnalysisTest(unittest.TestCase):
    def test_vacation_demo_handoff(self):
        result = analyze("직원들이 휴가를 신청하고 관리자가 승인할 수 있는 사내 휴가관리 서비스를 만들어줘.")
        self.assertEqual(result.analysis_mode, "mock")
        self.assertTrue(result.clarification_needed)
        self.assertTrue(all(r.source == "initial_input" for r in result.requirements))
        self.assertTrue(all(r.status == "confirmed" for r in result.requirements))
        self.assertTrue(all(not r.blocking for r in result.requirements))
        self.assertEqual([r.description for r in result.requirements if r.category == "role"],
                         ["직원 역할이 존재한다.", "관리자 역할이 존재한다."])
        self.assertTrue(all(g.related_requirement_ids for g in result.gaps))
        self.assertTrue(any(g.category == "modify_cancel" and g.blocking for g in result.gaps))

    def test_ambiguous_requirement_and_missing_topic_have_distinct_blocking(self):
        requirements = extract_requirements("승인자는 추후 결정. 사용자는 요청할 수 있다.", "project-1")
        gaps = analyze_gaps(requirements)
        unresolved = next(r for r in requirements if r.status == "needs_clarification")
        self.assertTrue(unresolved.blocking)
        self.assertTrue(all(not r.blocking for r in requirements if r.status == "confirmed"))
        self.assertTrue(any(unresolved.id in g.related_requirement_ids for g in gaps))
        self.assertTrue(any(g.category == "modify_cancel" and g.blocking for g in gaps))

    def test_no_blocking_gap(self):
        result = analyze("사용자는 공지사항을 조회할 수 있다.")
        self.assertFalse(result.clarification_needed)
        self.assertEqual(result.gaps, [])

    def test_nonblocking_gap_does_not_request_clarification(self):
        result = analyze("보안 정책은 추후 결정.")
        self.assertEqual(result.requirements[0].status, "needs_clarification")
        self.assertFalse(result.requirements[0].blocking)
        self.assertEqual(len(result.gaps), 1)
        self.assertFalse(result.gaps[0].blocking)
        self.assertFalse(result.clarification_needed)

    def test_confirmed_requirement_cannot_block(self):
        with self.assertRaises(ValidationError):
            Requirement(project_id="p", id="REQ-001", category="functional",
                        description="사용자는 조회할 수 있다.", status="confirmed",
                        source="initial_input", blocking=True)


if __name__ == "__main__":
    unittest.main()
