# NL-to-PRD

현재 구현은 M1의 첫 인계 지점입니다: 자연어 입력 → Requirement 추출·구조화 → Gap 분석 → 결과 표시. Clarification, Review, PRD 기능은 다음 담당 범위입니다.

## 로컬 실행

Python 3.12 이상, [uv](https://docs.astral.sh/uv/), Node.js가 필요합니다. 터미널 두 개에서 실행합니다.

```bash
cd backend
uv sync
LLM_PROVIDER=mock uv run uvicorn app.main:app --reload
```

```bash
cd frontend
npm ci
npm run dev
```

브라우저에서 `http://127.0.0.1:5173`을 엽니다. 프런트엔드 개발 서버가 `/api` 요청을 `127.0.0.1:8000`으로 전달합니다. 현재 Mock 실행에는 환경 변수가 필요하지 않습니다. `uv run python -m unittest discover -s tests -v`와 `npm run build`로 검증할 수 있습니다.

## SnowChat Demo 실행

루트의 `.env.example`을 `.env`로 복사하고 `FACTCHAT_API_KEY`에 개인 Key를 입력합니다. `.env`는 Git에서 제외됩니다. Key는 백엔드에서만 사용합니다.

```bash
cp .env.example .env
# .env를 편집한 다음:
cd backend
uv sync
uv run --env-file ../.env python -m app.smoke --models-only
uv run --env-file ../.env uvicorn app.main:app --reload
```

프런트엔드는 위와 같이 별도 터미널에서 실행합니다. 기존 Mock 백엔드가 켜져 있다면 중지한 뒤 SnowChat 명령으로 재시작합니다. `uv run --env-file`이 파일을 환경 변수로 로드합니다. 애플리케이션 자체는 `.env`를 자동으로 읽지 않습니다.

| 변수 | 의미 / 빈 값일 때 |
| --- | --- |
| `LLM_PROVIDER` | `mock` 또는 `snowchat`. 미설정 시 Mock. 예제 파일은 SnowChat |
| `FACTCHAT_API_KEY` | SnowChat에서 필수. 개인 API Gateway Key |
| `SNOWCHAT_BASE_URL` | 기본 `https://factchat-cloud.mindlogic.ai/v1/gateway` |
| `SNOWCHAT_EXTRACTION_MODEL` | 추출 모델. 빈 값이면 조회 결과에 있는 `gpt-5.6-luna` |
| `SNOWCHAT_GAP_MODEL` | Gap 모델. 빈 값이면 조회 결과에 있는 `gpt-5.6-luna` |
| `SNOWCHAT_EXTRACTION_REASONING` | 선택: `low`, `medium`, `high`; 빈 값은 모델 기본값 |
| `SNOWCHAT_GAP_REASONING` | 선택: `low`, `medium`, `high`; 빈 값은 모델 기본값 |

모델 목록은 `/models/?type=llm`에서 조회합니다. 기본 Luna가 없으면 실패하며 Terra나 Sol로 자동 전환하지 않습니다. 명시적인 모델 Override도 반환된 ID와 일치해야 합니다. 일반 분석 요청마다 목록을 한 번 조회하고 두 단계에서 재사용합니다. SnowChat 실패를 Mock 성공으로 바꾸지 않습니다.

Gateway 규격 근거: [숙명여대 인증](https://docs.mindlogic.ai/docs/sookmyung/api-gateway/getting-started/authentication), [모델 조회](https://docs.mindlogic.ai/docs/general/api-gateway/getting-started/models), [Chat Completions / Structured Output](https://docs.mindlogic.ai/docs/sookmyung/api-gateway/reference/chat-completions).

## 실제 호출 검증

다음 명령은 API 사용량이 발생합니다. 모델 조회 → 일반 Chat 1회 → 추출 → Gap 분석 순서로 검증하고, 원본 Usage와 Handoff JSON을 출력합니다. `--api-url`을 추가하면 실행 중인 API를 통해 분석을 한 번 더 수행합니다.

```bash
cd backend
uv run --env-file ../.env python -m app.smoke
uv run --env-file ../.env python -m app.smoke --api-url http://127.0.0.1:8000
```

브라우저에서 대표 입력을 제출하고 `SnowChat LLM 분석 결과` 표시와 Requirements/Gaps를 확인합니다. Unit Test는 환경의 Provider 설정과 무관하게 Mock 또는 가짜 Gateway 응답을 사용하며 외부 API를 호출하지 않습니다.

## 인계 계약 (초기 구현안)

`POST /api/requirements/analyze`에 `{ "text": "사용자는 공지사항을 조회할 수 있다." }`를 보냅니다. 공백뿐인 입력은 HTTP 422입니다. 응답 형태는 다음과 같습니다.

```json
{
  "project_id": "<UUID>",
  "run_id": "<UUID>",
  "clarification_round": 0,
  "requirements": [
    {
      "project_id": "<same UUID>",
      "id": "REQ-001",
      "category": "role",
      "description": "사용자 역할이 존재한다.",
      "status": "confirmed",
      "source": "initial_input",
      "blocking": false,
      "acceptance_criteria": []
    },
    {
      "project_id": "<same UUID>",
      "id": "REQ-002",
      "category": "functional",
      "description": "사용자는 공지사항을 조회할 수 있다.",
      "status": "confirmed",
      "source": "initial_input",
      "blocking": false,
      "acceptance_criteria": []
    }
  ],
  "gaps": [],
  "clarification_needed": false,
  "analysis_mode": "mock",
  "usage": []
}
```

현재 입력에서 명시된 내용만 `confirmed` Requirement로 기록합니다. 입력에서 관련 주제를 언급하면서 일부 조건을 미정으로 둔 경우에만 `needs_clarification` Requirement를 만듭니다. 전혀 언급하지 않은 주제는 Requirement를 만들지 않고 Gap으로 표현합니다. 이 단계는 AI Proposal과 Acceptance Criteria를 생성하지 않습니다.

`Requirement.blocking`은 해당 Requirement가 `needs_clarification`이고 해결 전 진행을 막을 때만 `true`입니다. `Gap.blocking`은 발견한 누락·모호성이 핵심 Clarification 대상일 때 `true`입니다. `clarification_needed`는 **Blocking Gap이 하나라도 있는지**로 계산합니다. 이 세 값은 서로 다른 의미입니다.

각 Gap은 `id`, `category`, `description`, `blocking`, `related_requirement_ids`를 가집니다. `related_requirement_ids`는 응답의 Requirement ID를 참조하며, 특정 Requirement와 연결되지 않은 서비스 전반의 누락이면 빈 배열입니다. 다음 담당자는 Gap과 연결된 Requirement를 사용해 질문을 만들 수 있습니다. 질문 문구와 답변 처리 정책은 이 계약에 포함하지 않습니다. ID는 분석 응답 안에서만 유효하며 영속 저장은 없습니다.

Requirement `category`는 다음 초기 Enum을 사용합니다. 이는 확정된 제품 요구사항이 아니라 현재 구현의 분류 계약입니다. 한 항목이 둘 이상에 해당하면 더 구체적인 의미를 우선합니다.

| Category | 의미 | 주로 연결되는 Gap 영역 |
| --- | --- | --- |
| `role` | 사용자·역할 자체 | `user_role` |
| `functional` | 사용자가 수행하는 기능 | `core_flow`, `modify_cancel` |
| `flow` | 단계의 순서 | `core_flow` |
| `permission` | 역할별 행위·승인 권한 | `permission_approval` |
| `state` | 상태와 상태 변화 | `state_change`, `modify_cancel` |
| `business_rule` | 다른 분류에 속하지 않는 업무 규칙 | `business_rule` |
| `exception` | 실패·예외 상황의 동작 | `exception_handling` |
| `scope` | 서비스에 포함하거나 제외할 범위 | `service_scope` |
| `integration` | 외부 시스템 연동 | `external_integration` |
| `nfr` | 성능·보안 등의 비기능 제약 | `nfr` |

Gap은 `AGENTS.md`의 8개 우선 확인 영역인 `user_role`, `core_flow`, `permission_approval`, `state_change`, `modify_cancel`, `exception_handling`, `service_scope`, `external_integration`을 사용합니다. 사용자가 직접 모호하게 남긴 일반 업무 규칙과 비기능 제약을 잃지 않도록 `business_rule`, `nfr`도 허용합니다. 이 분류와 Gap 설명을 다음 Clarification 단계의 입력으로 사용합니다.

## Provider와 단계별 구현

`backend/app/pipeline.py`가 Provider를 선택하고 `extract_stage` → `gap_stage`를 실행합니다. `llm/mock.py`는 기존 규칙 기반 시연을 보존하고 `llm/snowchat.py`는 인증·모델 조회·Gateway 통신만 담당합니다. 두 Provider 모두 같은 출력 검증 경로를 사용합니다. Mock은 문장 분리와 단어 규칙의 한계가 있으며 일반적인 의미 이해를 보장하지 않습니다.

추출 Prompt는 `backend/app/prompts/requirement_extraction.md`, Gap Prompt는 `backend/app/prompts/gap_analysis.md`입니다. `ExtractionOutput`과 `GapOutput`의 Pydantic JSON Schema를 `response_format`에 전달합니다. `strict: true`, 모든 필드 필수, `additionalProperties: false`를 사용하며 응답을 `model_validate_json`으로 검증합니다. Markdown 추출이나 실패 결과의 임의 보정은 없습니다. 프로젝트 ID, 중복 ID, Gap의 Requirement 참조와 미결정 Blocking Requirement의 Gap 누락도 검증합니다.

응답은 기존 Handoff 필드를 유지하고 `analysis_mode: mock|snowchat`, `usage`를 제공합니다. `usage`에는 단계별 `run_id`, `stage`, `model`, `latency`(초), `success`와 제공된 Token Usage가 들어갑니다. 위 예시의 빈 `usage`는 형태를 줄여 보여준 것입니다. 실제 실행에는 두 단계 기록이 있습니다. Gateway가 Usage를 주지 않으면 Token 수를 만들어 넣지 않습니다. 비용은 계산하지 않습니다. 실패 기록은 서버 로그에 남기며 사용자 화면에는 안전한 오류 메시지만 전달합니다.

구분되는 오류 코드는 `missing_api_key`, `authentication_failed`, `model_unavailable`, `rate_limit`, `gateway_error`, `timeout`, `request_rejected`, `structured_output_invalid`, `empty_response`, `incomplete_response`, `provider_refusal`, `invalid_config`입니다. 실패 시 전체 분석 결과를 성공으로 반환하지 않습니다.

다음 담당자는 `requirements`, `gaps`, `related_requirement_ids`를 사용해 Clarification을 이어갑니다. 질문 생성·답변 반영·Review·Proposal 수락·PRD·영속 저장은 구현하지 않았습니다.

실제 연결 및 브라우저 검증 결과는 [검증 기록](docs/snowchat-verification.md), 다음 단계에 전달할 전체 응답은 [실제 Handoff JSON](docs/examples/snowchat-handoff.json)을 참고하세요.