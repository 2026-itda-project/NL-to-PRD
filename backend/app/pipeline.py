import json
import logging
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from pydantic import ValidationError

from app.llm.errors import AnalysisError
from app.llm.mock import MockProvider
from app.llm.snowchat import SnowChatProvider
from app.schemas import AnalyzeResponse, ExtractionOutput, GapOutput

logger = logging.getLogger("uvicorn.error")
PROMPTS = Path(__file__).parent / "prompts"


def get_provider():
    mode = os.getenv("LLM_PROVIDER", "mock")
    if mode == "mock":
        return MockProvider()
    if mode == "snowchat":
        return SnowChatProvider()
    raise AnalysisError("invalid_config", "LLM_PROVIDER는 mock 또는 snowchat이어야 합니다.", 503)


def run_stage(provider, stage, payload, output_type, run_id, records):
    started = perf_counter()
    record = {"run_id": run_id, "stage": stage, "model": None, "success": False}
    try:
        record["model"] = provider.model_for(stage)
        content, usage = provider.complete(stage, (PROMPTS / f"{stage}.md").read_text(), payload, output_type, record["model"])
        if isinstance(usage, dict):
            record["usage"] = usage
            for source, target in [("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens")]:
                if isinstance(usage.get(source), int):
                    record[target] = usage[source]
        output = output_type.model_validate_json(content)
        if stage == "requirement_extraction":
            ids = [r.id for r in output.requirements]
            if len(ids) != len(set(ids)) or any(r.project_id != payload["project_id"] or not r.id.strip() or not r.description.strip() for r in output.requirements):
                raise AnalysisError("structured_output_invalid", "요구사항 식별자 또는 내용 검증에 실패했습니다.")
        else:
            ids = [g.id for g in output.gaps]
            known = {r["id"] for r in payload["requirements"]}
            if len(ids) != len(set(ids)) or any(not g.id.strip() or not g.description.strip() or not set(g.related_requirement_ids) <= known for g in output.gaps):
                raise AnalysisError("structured_output_invalid", "Gap 식별자 또는 요구사항 연결 검증에 실패했습니다.")
            covered = {rid for gap in output.gaps if gap.blocking for rid in gap.related_requirement_ids}
            if any(r["blocking"] and r["id"] not in covered for r in payload["requirements"]):
                raise AnalysisError("structured_output_invalid", "미결정 핵심 요구사항에 연결된 Blocking Gap이 누락됐습니다.")
        record["success"] = True
        return output
    except ValidationError as exc:
        record["error"] = "structured_output_invalid"
        # Log locations/types only: Pydantic input/context can contain user text or secrets.
        record["validation_errors"] = [{"loc": e["loc"], "type": e["type"]} for e in exc.errors()]
        raise AnalysisError("structured_output_invalid", "LLM 결과가 출력 Schema를 충족하지 않습니다.") from None
    except AnalysisError as exc:
        record["error"] = exc.code
        raise
    finally:
        record["latency"] = round(perf_counter() - started, 3)
        records.append(record)
        logger.info("analysis_stage %s", json.dumps(record, ensure_ascii=False))


def extract_stage(provider, text, project_id, run_id, records):
    return run_stage(provider, "requirement_extraction", {"text": text, "project_id": project_id}, ExtractionOutput, run_id, records).requirements


def gap_stage(provider, text, requirements, run_id, records):
    return run_stage(provider, "gap_analysis", {"text": text, "requirements": [r.model_dump() for r in requirements]}, GapOutput, run_id, records).gaps


def analyze(text, provider=None):
    provider = provider if provider is not None else get_provider()
    project_id, run_id = str(uuid4()), str(uuid4())
    records = []
    requirements = extract_stage(provider, text, project_id, run_id, records)
    gaps = gap_stage(provider, text, requirements, run_id, records)
    return AnalyzeResponse(project_id=project_id, run_id=run_id, requirements=requirements,
                           gaps=gaps, clarification_needed=any(g.blocking for g in gaps),
                           analysis_mode=provider.mode, usage=records)
