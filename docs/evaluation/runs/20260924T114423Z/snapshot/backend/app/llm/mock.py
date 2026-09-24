"""Deterministic rules used only by the explicitly selected Mock provider."""
# ponytail: keyword heuristics are demo-only; select SnowChat for semantic analysis.

import re

from app.schemas import Gap, GapCategory, Requirement, RequirementCategory


def category_for(clause: str) -> RequirementCategory:
    if re.search(r"승인|허가|권한|접근|approve|permission", clause, re.I):
        return "permission"
    if re.search(r"연동|외부 시스템|integration|external API", clause, re.I):
        return "integration"
    if re.search(r"오류|실패|예외|error|failure", clause, re.I):
        return "exception"
    if re.search(r"상태|대기|완료|반려|status", clause, re.I):
        return "state"
    if re.search(r"단계|순서|절차|흐름|workflow", clause, re.I):
        return "flow"
    if re.search(r"보안|성능|응답 시간|암호화|security|performance", clause, re.I):
        return "nfr"
    if re.search(r"규칙|정책|필수|금지|rule|policy", clause, re.I):
        return "business_rule"
    if re.search(r"역할|role", clause, re.I):
        return "role"
    if re.search(r"범위|제외|한정|scope", clause, re.I):
        return "scope"
    return "functional"


def extract_requirements(text: str, project_id: str) -> list[Requirement]:
    clauses = re.split(r"(?<=[.!?。])\s+|(?:하고|그리고|및)\s+", text.strip())
    requirements: list[Requirement] = []
    roles = dict.fromkeys(re.findall(
        r"(?:^|\s)(직원|관리자|사용자|고객|운영자|담당자|회원)(?:들)?(?:이|가|은|는)",
        text,
    ))
    for role in roles:
        requirements.append(Requirement(
            project_id=project_id,
            id=f"REQ-{len(requirements) + 1:03d}",
            category="role",
            description=f"{role} 역할이 존재한다.",
            status="confirmed",
            source="initial_input",
            blocking=False,
        ))
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        category = category_for(clause)
        unresolved = bool(re.search(r"미정|추후 결정|나중에 결정|상황에 따라|적절히|undecided|TBD", clause, re.I))
        requirements.append(Requirement(
            project_id=project_id,
            id=f"REQ-{len(requirements) + 1:03d}",
            category=category,
            description=clause,
            status="needs_clarification" if unresolved else "confirmed",
            source="initial_input",
            blocking=unresolved and category != "nfr",
        ))
    return requirements


def analyze_gaps(requirements: list[Requirement]) -> list[Gap]:
    gaps: list[Gap] = []

    def add(category: GapCategory, description: str, blocking: bool, related: list[str]) -> None:
        gaps.append(Gap(
            id=f"GAP-{len(gaps) + 1:03d}",
            related_requirement_ids=related,
            category=category,
            description=description,
            blocking=blocking,
        ))

    category_to_gap: dict[RequirementCategory, GapCategory] = {
        "role": "user_role", "functional": "core_flow", "flow": "core_flow",
        "permission": "permission_approval", "state": "state_change",
        "business_rule": "business_rule", "exception": "exception_handling",
        "scope": "service_scope", "integration": "external_integration",
        "nfr": "nfr",
    }
    for requirement in requirements:
        if requirement.status == "needs_clarification":
            add(category_to_gap[requirement.category],
                f"명시된 내용의 결정 또는 조건이 불분명합니다: {requirement.description}",
                requirement.blocking, [requirement.id])

    descriptions = " ".join(requirement.description for requirement in requirements)
    request_ids = [r.id for r in requirements if re.search(r"신청|요청|예약|주문|결제|request|book|order|pay", r.description, re.I)]
    if request_ids and not re.search(r"수정|변경|취소|modify|edit|cancel", descriptions, re.I):
        add("modify_cancel", "신청·요청 등의 수정 또는 취소 가능 여부가 명시되지 않았습니다.", True, request_ids)

    approval_ids = [r.id for r in requirements if re.search(r"승인|허가|approve", r.description, re.I)]
    if approval_ids and not re.search(r"관리자|담당자|운영자|승인자|manager|admin|approver", descriptions, re.I):
        add("permission_approval", "승인 권한을 가진 역할이 명시되지 않았습니다.", True, approval_ids)

    if request_ids and not approval_ids and not re.search(r"처리|완료|상태|process|complete|status", descriptions, re.I):
        add("core_flow", "신청·요청 이후의 핵심 처리 흐름이 명시되지 않았습니다.", True, request_ids)

    return gaps


class MockProvider:
    mode = "mock"

    def model_for(self, stage):
        return None

    def complete(self, stage, prompt, payload, output_type, model):
        if stage == "requirement_extraction":
            result = {"requirements": [r.model_dump() for r in extract_requirements(payload["text"], payload["project_id"])]}
        else:
            requirements = [Requirement.model_validate(r) for r in payload["requirements"]]
            result = {"gaps": [g.model_dump() for g in analyze_gaps(requirements)]}
        return output_type.model_validate(result).model_dump_json(), None
