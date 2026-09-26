import logging

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from app.pipeline import analyze, clarify_step, review_step
from app.llm.errors import AnalysisError
from app.schemas import (
    AnalyzeRequest, AnalyzeResponse, ClarificationStepRequest, ReviewRequest, ReviewResponse, WorkflowState,
)

app = FastAPI(title="NL-to-PRD M1 input analysis")


@app.post("/api/requirements/analyze", response_model=AnalyzeResponse)
def analyze_requirements(request: AnalyzeRequest) -> AnalyzeResponse:
    if not request.text.strip():
        raise HTTPException(status_code=422, detail="text must not be blank")
    try:
        return analyze(request.text)
    except AnalysisError as exc:
        logging.getLogger("uvicorn.error").warning("analysis_failed code=%s", exc.code)
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message}) from None


def http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AnalysisError):
        logging.getLogger("uvicorn.error").warning("analysis_failed code=%s", exc.code)
        return HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message})
    # Workflow rule messages are fixed text; Pydantic messages may contain client input.
    message = "요청 상태가 검증 규칙을 충족하지 않습니다." if isinstance(exc, ValidationError) else str(exc)
    return HTTPException(status_code=422, detail={"code": "invalid_state", "message": message})


@app.post("/api/clarification/step", response_model=WorkflowState)
def clarification_step(request: ClarificationStepRequest) -> WorkflowState:
    try:
        return clarify_step(request.state, request.answers)
    except (AnalysisError, ValueError) as exc:
        raise http_error(exc) from None


@app.post("/api/review", response_model=ReviewResponse)
def review(request: ReviewRequest) -> ReviewResponse:
    try:
        state, reviewed = review_step(request.state, request.action)
    except ValueError as exc:
        raise http_error(exc) from None
    return ReviewResponse(state=state, reviewed=reviewed)
