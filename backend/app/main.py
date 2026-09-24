import logging

from fastapi import FastAPI, HTTPException

from app.pipeline import analyze
from app.llm.errors import AnalysisError
from app.schemas import AnalyzeRequest, AnalyzeResponse

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
