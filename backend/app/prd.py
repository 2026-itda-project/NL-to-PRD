"""PRD 생성·검증. ReviewedRequirements를 받아 PRD로 조립한다."""
from app.schemas import Requirement

SECTION_BY_CATEGORY = {
    "role": "roles", "flow": "user_flows", "functional": "functional_requirements",
    "permission": "business_rules", "business_rule": "business_rules",
    "state": "business_rules", "exception": "business_rules",
    "nfr": "nfrs", "scope": "in_scope", "integration": "in_scope",
}


def section_for(req: Requirement) -> str:
    if req.status == "proposed":
        return "assumptions"
    if req.status == "needs_clarification":
        return "open_issues"
    return SECTION_BY_CATEGORY[req.category]