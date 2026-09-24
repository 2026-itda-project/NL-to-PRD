"""Explicit, billable smoke test. Unit tests never invoke this module."""

import argparse
import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.llm.errors import AnalysisError
from app.llm.snowchat import SnowChatProvider
from app.pipeline import analyze
from app.schemas import AnalyzeResponse

DEMO = "직원들이 휴가를 신청하고 관리자가 승인할 수 있는 사내 휴가관리 서비스를 만들어줘."


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models-only", action="store_true")
    parser.add_argument("--api-url", help="Optional running FastAPI or Vite origin, e.g. http://127.0.0.1:8000")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        provider = SnowChatProvider()
        models = provider.list_models()
        print(json.dumps({"authentication": "success", "models": models,
                          "availability": {m: m in models for m in ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"]}}, ensure_ascii=False))
        if args.models_only:
            return
        selected = {stage: provider.model_for(stage) for stage in ["requirement_extraction", "gap_analysis"]}
        print(json.dumps({"selected_models": selected}))
        chat = provider.request("/chat/completions/", {
            "model": selected["requirement_extraction"],
            "messages": [{"role": "user", "content": "Reply with OK."}],
        })
        print(json.dumps({"chat": provider.content(chat), "usage": chat.get("usage")}))
        result = analyze(DEMO, provider)
        print(result.model_dump_json(indent=2))
        if args.api_url:
            request = Request(args.api_url.rstrip("/") + "/api/requirements/analyze",
                              data=json.dumps({"text": DEMO}).encode(), headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=240) as response:
                result = AnalyzeResponse.model_validate_json(response.read())
            if result.analysis_mode != "snowchat":
                raise AnalysisError("wrong_provider", "API가 SnowChat 모드가 아닙니다.")
            print(json.dumps({"api_end_to_end": "success"}))
            print(result.model_dump_json(indent=2))
    except AnalysisError as exc:
        print(json.dumps({"success": False, "code": exc.code, "message": exc.message}, ensure_ascii=False))
        raise SystemExit(1) from None
    except (HTTPError, URLError, TimeoutError):
        print(json.dumps({"success": False, "code": "api_smoke_failed", "message": "API 서버 응답과 실행 설정을 확인해주세요."}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
