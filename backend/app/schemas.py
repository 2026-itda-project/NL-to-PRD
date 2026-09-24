from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RequirementCategory = Literal[
    "role", "functional", "flow", "permission", "state", "business_rule",
    "exception", "scope", "integration", "nfr",
]
GapCategory = Literal[
    "user_role", "core_flow", "permission_approval", "state_change",
    "modify_cancel", "exception_handling", "service_scope", "external_integration",
    "business_rule", "nfr",
]


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_id: str
    id: str
    category: RequirementCategory
    description: str
    status: Literal["confirmed", "needs_clarification", "proposed"]
    source: str
    blocking: bool
    acceptance_criteria: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def blocking_requires_clarification(self):
        if self.blocking and self.status != "needs_clarification":
            raise ValueError("blocking Requirement must need clarification")
        return self


class Gap(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str
    related_requirement_ids: list[str]
    category: GapCategory
    description: str
    blocking: bool


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1)


class AnalyzeResponse(BaseModel):
    project_id: str
    run_id: str
    clarification_round: int = 0
    requirements: list[Requirement]
    gaps: list[Gap]
    clarification_needed: bool
    analysis_mode: Literal["mock", "snowchat"] = "mock"
    usage: list[dict] = Field(default_factory=list)


class InitialRequirement(Requirement):
    status: Literal["confirmed", "needs_clarification"]
    source: Literal["initial_input"]
    acceptance_criteria: list[str]


class ExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    requirements: list[InitialRequirement]


class GapOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    gaps: list[Gap]
