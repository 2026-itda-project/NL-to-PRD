# NL-to-PRD

현재 구현은 M1의 두 번째 인계 지점입니다: 자연어 입력 → Requirement 추출·구조화 → Gap 분석 → Clarification(최대 3라운드) → Requirement Review·승인 → `ReviewedRequirements` 인계. PRD 생성·검증은 다음 담당 범위입니다.

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
| `SNOWCHAT_GAP_MODEL` | Gap 분석·질문 생성·답변 반영 모델. 빈 값이면 조회 결과에 있는 `gpt-5.6-luna` |
| `SNOWCHAT_EXTRACTION_REASONING` | 선택: `low`, `medium`, `high`; 빈 값은 모델 기본값 |
| `SNOWCHAT_GAP_REASONING` | 선택: `low`, `medium`, `high`; 빈 값은 모델 기본값. 추출 외 모든 단계에 적용 |

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

`backend/app/pipeline.py`가 Provider를 선택하고 `extract_stage` → `gap_stage`를 실행합니다. Clarification은 같은 파일의 `question_stage`·`update_stage`를 추가로 사용합니다(Prompt: `question_generation.md`, `requirement_update.md`). `llm/mock.py`는 기존 규칙 기반 시연을 보존하고 `llm/snowchat.py`는 인증·모델 조회·Gateway 통신만 담당합니다. 두 Provider 모두 같은 출력 검증 경로를 사용합니다. Mock은 문장 분리와 단어 규칙의 한계가 있으며 일반적인 의미 이해를 보장하지 않습니다.

추출 Prompt는 `backend/app/prompts/requirement_extraction.md`, Gap Prompt는 `backend/app/prompts/gap_analysis.md`입니다. `ExtractionOutput`과 `GapOutput`의 Pydantic JSON Schema를 `response_format`에 전달합니다. `strict: true`, 모든 필드 필수, `additionalProperties: false`를 사용하며 응답을 `model_validate_json`으로 검증합니다. Markdown 추출이나 실패 결과의 임의 보정은 없습니다. 프로젝트 ID, 중복 ID, Gap의 Requirement 참조와 미결정 Blocking Requirement의 Gap 누락도 검증합니다.

응답은 기존 Handoff 필드를 유지하고 `analysis_mode: mock|snowchat`, `usage`를 제공합니다. `usage`에는 단계별 `project_id`, `run_id`, `stage`, `model`, `latency`(초), `success`, `started_at`·`ended_at`(ISO 8601 UTC), `cost`와 제공된 Token Usage가 들어갑니다. 위 예시의 빈 `usage`는 형태를 줄여 보여준 것입니다. 실제 분석에는 두 단계 기록이 있고, Clarification 라운드마다 기록이 누적됩니다. Gateway가 Usage를 주지 않으면 Token 수를 만들어 넣지 않습니다. 비용은 계산하지 않으며 `cost`는 항상 `null`입니다. 실패 기록은 서버 로그에 남기며 사용자 화면에는 안전한 오류 메시지만 전달합니다.

구분되는 오류 코드는 `missing_api_key`, `authentication_failed`, `model_unavailable`, `rate_limit`, `gateway_error`, `timeout`, `request_rejected`, `structured_output_invalid`, `empty_response`, `incomplete_response`, `provider_refusal`, `invalid_config`입니다. 실패 시 전체 분석 결과를 성공으로 반환하지 않습니다.

분석 결과는 아래 Clarification·Review 단계가 이어받습니다. PRD 생성·검증과 영속 저장은 구현하지 않았습니다.

실제 연결 및 브라우저 검증 결과는 [검증 기록](docs/snowchat-verification.md), 분석 단계의 실제 응답 전체는 [실제 Handoff JSON](docs/examples/snowchat-handoff.json)을 참고하세요.

## Clarification·Review 인계 계약 (초기 구현안)

AGENTS.md 7~10장을 구현한 부분입니다. Endpoint, 필드, `source` 값, metrics 정의는 확정된 제품 요구사항이 아니라 현재 구현의 계약입니다.

### API

상태는 stateless 왕복 방식입니다. 클라이언트가 `WorkflowState` 전체를 보내고 서버는 요청마다 다시 검증한 뒤 새 상태를 돌려줍니다. 영속 저장이 없기 때문이며, 클라이언트가 상태를 조작할 수 있다는 한계는 데모에서 허용합니다. DB를 도입하면 `project_id`로 상태를 읽고 같은 순수 함수(`backend/app/workflow.py`)를 적용하면 됩니다.

| Endpoint | 요청 | 응답 | LLM 호출 |
| --- | --- | --- | --- |
| `POST /api/clarification/step` | `{state, answers?}` | `WorkflowState` | 있음 |
| `POST /api/review` | `{state, action}` | `{state, reviewed}` (`reviewed`는 승인 때만, 그 외 `null`) | 없음 |

`WorkflowState`는 분석 응답에 `text`, `phase`(`clarifying` → `review` → `approved`), `questions`(답변을 기다리는 질문 `{gap_id, question, ai_proposal}`), `history`(라운드별 `{round, gaps, questions, answers}`), `edit_count`를 더한 형태입니다. 분석 직후 `{...분석 응답, text}`를 `answers` 없이 보내면 첫 질문을 받습니다. 이후에는 `answers: [{gap_id, answer}]`를 보냅니다.

오류:
- phase 불일치, 현재 질문에 없거나 중복된 `gap_id`, 답변 라운드에 `answers` 누락, 상태 불변식 위반(Requirement id 중복, `project_id` 불일치 등): HTTP 422 `{"detail": {"code": "invalid_state", "message": ...}}`
- 요청 형식 오류: FastAPI 기본 422 형식
- LLM 오류: 분석과 같은 오류 코드

### Clarification 규칙

- Blocking Gap이 있으면 Gap마다 질문 1개를 만듭니다. Non-blocking Gap만 남으면 질문하지 않고 Review로 넘어갑니다.
- 라운드는 최대 3회입니다. 빈 답변은 건너뜀이며 해당 Blocking이 남아 다음 라운드에 다시 질문합니다. 건너뛴 라운드도 1회로 셉니다. 빠진 답변은 빈 답변으로 채우며, `answers: []`는 전부 건너뜀입니다.
- 모든 답변이 빈 라운드는 답변 반영과 Gap 재분석을 생략하고 기존 Gap으로 질문만 다시 만듭니다.
- 답변은 새 `confirmed` Requirement(`source=clarification_answer`)로 추가하거나, 연결된 `needs_clarification` 또는 이전 답변 항목을 교체합니다. `initial_input`·`review_input`·`proposed` 항목은 답변 반영으로 바뀌지 않습니다. 답변이 명시하지 않은 내용은 만들지 않습니다. Acceptance Criteria는 항상 비워 두며, 출력에 AC가 있으면 `structured_output_invalid`로 거부합니다. AC는 사용자가 Review에서 입력합니다.
- Gap은 라운드마다 다시 분석하므로 Gap ID가 바뀔 수 있습니다. 과거 질문·답변은 `history`의 Gap과 함께 봅니다.
- 3라운드 뒤에도 남은 Blocking Gap은 `status=proposed`, `source=ai_proposal`, `blocking=false` Requirement로 전환합니다. AI Proposal이 `confirmed`로 바로 들어가는 경로는 없습니다.
- `phase`가 `review` 이후이면 `clarification_needed=false`입니다. 이때 `gaps`는 마지막 분석 결과 그대로라 `blocking=true`가 남아 있을 수 있습니다. **Review 이후에는 `gaps`가 아니라 `requirements`의 `status`·`blocking`을 기준으로 판단합니다.**

### Review 작업

`action`은 `type` 필드로 구분합니다. `review` phase에서만 가능하며 승인 후에는 모든 작업을 거부합니다.

| `type` | 필드 | 동작 |
| --- | --- | --- |
| `accept` | `ids` | `proposed`만 `confirmed`·`blocking=false`로 변경. 1개면 개별, 여러 개면 일괄 수락. `source`는 유지 |
| `edit` | `id`, `description?`, `category?`, `acceptance_criteria?`, `confirm` | 내용 수정, `edit_count` +1. `confirm=true`면 `confirmed`·`blocking=false`. `source`는 바꾸지 않으며 `proposed`를 만들 수 없음 |
| `add` | `category`, `description`, `acceptance_criteria` | 새 `confirmed` Requirement(`source=review_input`), `edit_count` +1 |
| `approve` | 없음 | `needs_clarification`이면서 `blocking=true`인 항목이 있으면 거부. 수락하지 않은 `proposed`가 있어도 승인. `phase=approved`, `reviewed` 반환 |

삭제 작업은 없습니다. 사용자가 확인하지 않은 `proposed`도 삭제하지 않습니다(AGENTS 9장).

### `source` 값

`source`는 내용의 출처입니다. 수락하거나 수정해도 바뀌지 않습니다. 확정 여부는 `status`로 판단합니다.

| `source` | 의미 |
| --- | --- |
| `initial_input` | 최초 입력에서 추출 |
| `clarification_answer` | Clarification 답변에서 반영 |
| `ai_proposal` | 3라운드 후 AI 기본값 제안. `confirmed`이면 사용자가 수락한 것 |
| `review_input` | Review에서 사용자가 추가 |

### `ReviewedRequirements` (PRD 단계 입력)

```json
{
  "project_id": "<UUID>",
  "run_id": "<UUID>",
  "requirements": [
    { "project_id": "<UUID>", "id": "REQ-003", "category": "state", "description": "...", "status": "confirmed", "source": "ai_proposal", "blocking": false, "acceptance_criteria": [] },
    { "project_id": "<UUID>", "id": "REQ-004", "category": "permission", "description": "...", "status": "proposed", "source": "ai_proposal", "blocking": false, "acceptance_criteria": [] }
  ],
  "metrics": { "question_count": 6, "turn_count": 3, "edit_count": 1, "unaccepted_proposal_count": 1 }
}
```

| metric | 정의 |
| --- | --- |
| `question_count` | 사용자에게 보인 질문 수(`history` 합). 3라운드 후 Proposal 생성용 질문은 제외 |
| `turn_count` | 답변을 제출한 라운드 수(`len(history)`) |
| `edit_count` | Review 단계의 수정·추가 횟수(프로젝트 전체). PRD 단계의 "최종 PRD 사용자 수정량"과는 다른 지표 |
| `unaccepted_proposal_count` | 승인 시점에 남은 `proposed` 수 |

PRD 단계에서 참고할 점:
- 수락하지 않은 `proposed`는 `blocking=false`이므로 AGENTS 17장의 "미해결 Blocking Requirement"가 아닙니다. PRD의 **Assumptions** 후보입니다.
- `blocking=true`인 `needs_clarification`은 승인 조건상 인계물에 없습니다. `blocking=false`인 `needs_clarification`은 **Open Issues** 후보입니다.
- `confirmed` + `ai_proposal`은 사용자가 승인한 AI 제안입니다. 그대로 수락했는지 수정 후 확정했는지는 항목 단위로 구분되지 않습니다.
- Acceptance Criteria는 최초 입력에 명시된 것과 사용자가 Review에서 입력한 것만 있습니다. Clarification과 AI Proposal은 AC를 만들지 않으므로 대부분 비어 있습니다.

실제 SnowChat 실행 기록은 [Review 인계 JSON](docs/examples/review-handoff.json)입니다. 대표 데모 입력으로 2026-09-26에 실행했고, Gap 분석 Prompt 수정 전 결과입니다. 1라운드에 답변하고 2·3라운드는 건너뛰었습니다(질문 6 → 9 → 9, Proposal 9개 중 4개 수락). REQ-029의 AC는 Review 수정 기능을 확인하면서 사용자가 입력한 값이며, 항목 내용(기간 중복 금지)과는 관련이 없습니다. 답변 반영의 AC 제한을 추가하기 전 실행이라 REQ-006~020에는 LLM이 만든 AC가 들어 있습니다. 현재 동작에서는 이 AC가 생기지 않으며, 사용자가 확정한 AC로 보지 않습니다. 이 파일은 테스트 fixture로 사용하지 않습니다.