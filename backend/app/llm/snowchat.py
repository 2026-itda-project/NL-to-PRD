"""Gateway transport only; stage prompts and contracts belong to services."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

from app.llm.errors import AnalysisError

BASE_URL = "https://factchat-cloud.mindlogic.ai/v1/gateway"
PREFERRED_MODEL = "gpt-5.6-luna"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward credentials to a redirected host.


class SnowChatProvider:
    mode = "snowchat"

    def __init__(self):
        self.key = os.getenv("FACTCHAT_API_KEY", "").strip()
        if not self.key:
            raise AnalysisError("missing_api_key", "SnowChat API Key가 설정되지 않았습니다.", 503)
        self.base_url = (os.getenv("SNOWCHAT_BASE_URL") or BASE_URL).rstrip("/")
        if not self.base_url.startswith("https://"):
            raise AnalysisError("invalid_config", "Gateway 주소는 HTTPS여야 합니다.", 503)
        self.models = None
        self.opener = build_opener(NoRedirect())

    def request(self, path, payload=None):
        request = Request(self.base_url + path,
                          data=None if payload is None else json.dumps(payload).encode(),
                          headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json",
                                   "Accept": "application/json", "User-Agent": "NL-to-PRD/0.1"})
        try:
            with self.opener.open(request, timeout=90) as response:
                return json.load(response)
        except HTTPError as exc:
            errors = {
                401: ("authentication_failed", "SnowChat 인증에 실패했습니다.", 502),
                403: ("model_unavailable", "모델 또는 Gateway 접근 권한이 없습니다.", 502),
                404: ("model_unavailable", "모델 또는 Gateway 경로를 확인해주세요.", 502),
                429: ("rate_limit", "SnowChat 사용량 제한입니다. 잠시 후 다시 시도해주세요.", 429),
                400: ("request_rejected", "Gateway가 요청 또는 Structured Output 설정을 거부했습니다.", 502),
            }
            code, message, status = errors.get(exc.code, ("gateway_error", "SnowChat Gateway 오류가 발생했습니다.", 502))
            raise AnalysisError(code, message, status) from None
        except TimeoutError:
            raise AnalysisError("timeout", "SnowChat 응답 시간이 초과되었습니다.", 504) from None
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise AnalysisError("timeout", "SnowChat 응답 시간이 초과되었습니다.", 504) from None
            raise AnalysisError("gateway_error", "SnowChat에 연결할 수 없습니다.") from None
        except (ValueError, UnicodeError):
            raise AnalysisError("gateway_error", "Gateway 응답 형식이 올바르지 않습니다.") from None

    def list_models(self):
        result = self.request("/models/?type=llm")
        try:
            models = [item["id"] for item in result["data"] if item.get("type", "llm") == "llm"]
            if not all(isinstance(model, str) and model for model in models):
                raise ValueError
        except (KeyError, TypeError, ValueError, AttributeError):
            raise AnalysisError("gateway_error", "모델 목록 응답 형식이 올바르지 않습니다.") from None
        self.models = models
        return models

    def model_for(self, stage):
        models = self.models if self.models is not None else self.list_models()
        variable = "SNOWCHAT_EXTRACTION_MODEL" if stage == "requirement_extraction" else "SNOWCHAT_GAP_MODEL"
        selected = os.getenv(variable) or PREFERRED_MODEL
        if selected not in models:
            raise AnalysisError("model_unavailable", "선택한 모델이 계정의 모델 목록에 없습니다. 모델 조회 결과와 설정을 확인해주세요.", 503)
        return next(model for model in models if model == selected)

    def complete(self, stage, prompt, payload, output_type, model):
        body = {
            "model": model,
            "messages": [{"role": "system", "content": prompt},
                         {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": output_type.__name__, "strict": True, "schema": output_type.model_json_schema(),
            }},
        }
        variable = "SNOWCHAT_EXTRACTION_REASONING" if stage == "requirement_extraction" else "SNOWCHAT_GAP_REASONING"
        reasoning = os.getenv(variable, "").strip()
        if reasoning:
            if reasoning not in {"low", "medium", "high"}:
                raise AnalysisError("invalid_config", "추론 설정은 low, medium, high 중 하나여야 합니다.", 503)
            body["reasoning_effort"] = reasoning
        result = self.request("/chat/completions/", body)
        return self.content(result), result.get("usage")

    @staticmethod
    def content(result):
        try:
            choice = result["choices"][0]
            message = choice["message"]
            if message.get("refusal"):
                raise AnalysisError("provider_refusal", "모델이 분석 요청을 처리하지 못했습니다.")
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                raise AnalysisError("empty_response", "모델의 응답이 비어 있습니다.")
            if choice.get("finish_reason") != "stop":
                raise AnalysisError("incomplete_response", "모델 응답이 완성되지 않았습니다.")
            return content
        except (KeyError, IndexError, TypeError, AttributeError):
            raise AnalysisError("gateway_error", "Gateway 응답 형식이 올바르지 않습니다.") from None
