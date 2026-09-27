"""PRD 생성·검증. ReviewedRequirements를 받아 PRD로 조립한다."""
from app.schemas import PRD, AcceptanceCriterion, PRDItem, ProductOverview, Requirement, ReviewedRequirements

SECTION_BY_CATEGORY = {
    "role": "roles", "flow": "user_flows", "functional": "functional_requirements",
    "permission": "business_rules", "business_rule": "business_rules",
    "state": "business_rules", "exception": "business_rules",
    "nfr": "nfrs", "scope": "in_scope", "integration": "in_scope",
}

PREFIX_BY_SECTION = {
    "in_scope": "SCOPE", "roles": "ROLE", "user_flows": "US",
    "functional_requirements": "FR", "business_rules": "RULE", "nfrs": "NFR",
    "assumptions": "ASM", "open_issues": "ISSUE",
}


def section_for(req: Requirement) -> str:
    if req.status == "proposed":
        return "assumptions"
    if req.status == "needs_clarification":
        return "open_issues"
    return SECTION_BY_CATEGORY[req.category]


def build_prd(reviewed: ReviewedRequirements, overview: ProductOverview) -> PRD:
    sections = {name: [] for name in PREFIX_BY_SECTION}
    criteria = []
    for req in reviewed.requirements:
        name = section_for(req)
        number = len(sections[name]) + 1
        item = PRDItem(id=f"{PREFIX_BY_SECTION[name]}-{number:03d}",
                       description=req.description, source_requirement_ids=[req.id])
        sections[name].append(item)
        if name not in ("assumptions", "open_issues"):
            for text in req.acceptance_criteria:
                criteria.append(AcceptanceCriterion(
                    id=f"AC-{len(criteria) + 1:03d}", description=text,
                    target_id=item.id, source_requirement_ids=[req.id]))
    return PRD(project_id=reviewed.project_id, run_id=reviewed.run_id, overview=overview,
               out_of_scope=[], acceptance_criteria=criteria, **sections)