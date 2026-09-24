"""Explicit, billable 36-slot evaluation. No production pipeline changes."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RETRY = {'timeout', 'rate_limit', 'gateway_error'}
STOP = {'missing_api_key', 'authentication_failed', 'model_unavailable', 'invalid_config'}
GAP_ERROR = '미결정 핵심 요구사항에 연결된 Blocking Gap이 누락됐습니다'
SCHEMA_ERROR = 'LLM 결과가 출력 Schema를 충족하지 않습니다'


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def classify(code, message):
    normalized = message.strip().rstrip('.').strip()
    if code == 'structured_output_invalid':
        if normalized == GAP_ERROR:
            return 'blocking_gap_missing'
        if normalized == SCHEMA_ERROR:
            return 'json_schema_indistinguishable'
        return 'other_contract_unknown'
    return code


def delay(attempt, header=None):
    if header:
        try:
            if header.isdigit():
                return float(header)
            return max(0, (parsedate_to_datetime(header) - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            pass
    return (5, 15)[attempt - 1]


def run_slot(call, sleep=time.sleep):
    records = []
    for attempt in range(1, 4):
        record = call()
        record['attempt'] = attempt
        records.append(record)
        if record['code'] not in RETRY or attempt == 3:
            break
        seconds = delay(attempt, record.get('retry_after'))
        record['retry_wait_seconds'] = seconds
        sleep(seconds)
    return records


def cases():
    text = (HERE / 'scenarios-draft.md').read_text()
    assert text.startswith('# 시나리오, 정답 v1.0')
    result = []
    for cid, body in re.findall(r'^## ([LRESAD]\d{2}) -[^\n]*\n(.*?)(?=^## |\Z)', text, re.M | re.S):
        inputs = re.findall(r'^> (.*)$', body, re.M)
        assert len(inputs) == 1, cid
        result.append({'id': cid, 'text': inputs[0]})
    assert len(result) == len({c['id'] for c in result}) == 12
    assert text.count('| 승인 |') == 12
    return result


def environment():
    env = os.environ.copy()
    allowed = {'FACTCHAT_API_KEY', 'SNOWCHAT_BASE_URL'}
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip().removeprefix('export ')
            key, sep, value = line.partition('=')
            if sep and key.strip() in allowed and key.strip() not in env:
                values = shlex.split(value, comments=True)
                if len(values) > 1:
                    raise ValueError('환경 변수 값은 공백을 포함하면 따옴표로 감싸야 합니다.')
                env[key.strip()] = values[0] if values else ''
    env['LLM_PROVIDER'] = 'snowchat'
    for stage in ('EXTRACTION', 'GAP'):
        env['SNOWCHAT_' + stage + '_MODEL'] = 'gpt-5.6-luna'
        env['SNOWCHAT_' + stage + '_REASONING'] = ''
    return env


def contract(body):
    from app.schemas import AnalyzeResponse, InitialRequirement, Gap
    value = AnalyzeResponse.model_validate(body)
    assert value.analysis_mode == 'snowchat'
    reqs = [InitialRequirement.model_validate(r) for r in body['requirements']]
    gaps = [Gap.model_validate(g) for g in body['gaps']]
    ids = [r.id for r in reqs]
    assert len(ids) == len(set(ids))
    assert all(r.project_id == value.project_id and r.id.strip() and r.description.strip() for r in reqs)
    assert len({g.id for g in gaps}) == len(gaps)
    assert all(g.id.strip() and g.description.strip() and set(g.related_requirement_ids) <= set(ids) for g in gaps)
    covered = {rid for g in gaps if g.blocking for rid in g.related_requirement_ids}
    assert all(not r.blocking or r.id in covered for r in reqs)
    assert value.clarification_needed == any(g.blocking for g in gaps)
    assert [u.get('stage') for u in value.usage] == ['requirement_extraction', 'gap_analysis']
    assert all(u.get('model') == 'gpt-5.6-luna' and u.get('success') for u in value.usage)


def request(origin, text, secret):
    started = now()
    tick = time.perf_counter()
    req = Request(origin + '/api/requirements/analyze', data=json.dumps({'text': text}).encode(), headers={'Content-Type': 'application/json'})
    try:
        try:
            response = urlopen(req, timeout=600)
        except HTTPError as exc:
            response = exc
        with response:
            raw = response.read().decode('utf-8')
            if secret:
                raw = raw.replace(secret, '[REDACTED]')
            status, retry_after = response.status, response.headers.get('Retry-After')
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        detail = body.get('detail', {}) if isinstance(body, dict) else {}
        code = 'success' if status == 200 else (detail.get('code', 'unclassified_api_error') if isinstance(detail, dict) else 'unclassified_api_error')
        message = detail.get('message', '') if isinstance(detail, dict) else ''
        if status == 200:
            try:
                contract(body)
            except Exception:
                code, message = 'evaluation_contract_failed', '응답의 자동 계약 검사 실패'
        return {'started_at': started, 'ended_at': now(), 'latency_seconds': round(time.perf_counter()-tick, 3),
                'http_status': status, 'code': code, 'error_type': classify(code, message),
                'response': body, 'raw_response': raw, 'retry_after': retry_after}
    except (URLError, TimeoutError, OSError, UnicodeError):
        return {'started_at': started, 'ended_at': now(), 'latency_seconds': round(time.perf_counter()-tick, 3),
                'http_status': None, 'code': 'runner_transport_error', 'error_type': 'runner_transport_error',
                'response': None, 'raw_response': None, 'retry_after': None}


def summarize(out, manifest, attempts):
    finals = {}
    first = {}
    tokens = {'input_tokens': 0, 'output_tokens': 0}
    missing_usage = 0
    for a in attempts:
        finals[a['slot_id']] = a
        first.setdefault(a['slot_id'], a)
        usage = (a.get('response') or {}).get('usage', [])
        complete = len(usage) == 2
        for u in usage:
            for field in tokens:
                v = u.get(field)
                if isinstance(v, int) and not isinstance(v, bool):
                    tokens[field] += v
                else:
                    complete = False
        if not complete:
            missing_usage += 1
    summary = {'state': manifest['state'], 'planned_slots': 36, 'attempted_slots': len(finals),
               'unexecuted_slots': 36-len(finals), 'attempts': len(attempts),
               'first_success_slots': sum(a['code']=='success' for a in first.values()),
               'final_success_slots': sum(a['code']=='success' for a in finals.values()),
               'retry_attempts': len(attempts)-len(finals), 'observed_tokens': tokens,
               'usage_unknown_attempts': missing_usage,
               'total_consumed_tokens': None if missing_usage else sum(tokens.values()),
               'attempt_errors': dict(Counter(a['error_type'] for a in attempts if a['code']!='success')),
               'final_slot_errors': dict(Counter(a['error_type'] for a in finals.values() if a['code']!='success')),
               'semantic_scoring': 'pending_human_review'}
    write_json(out/'summary.json', summary)
    lines = ['# 평가 실행 보고서', '',
             f"실행 ID: `{manifest['evaluation_id']}`", '',
             '**자동 실행 및 계약 검사 결과. 의미 채점은 검토 전이며 품질 점수가 아니다.**', '',
             f"- 상태: {summary['state']}", f"- 최초 성공: {summary['first_success_slots']}/36슬롯",
             f"- 최종 성공: {summary['final_success_slots']}/36슬롯",
             f"- 호출 시도: {len(attempts)}, 재시도: {summary['retry_attempts']}, 미실행: {summary['unexecuted_slots']}",
             f"- 응답에서 확인 가능한 Token: 입력 {tokens['input_tokens']}, 출력 {tokens['output_tokens']}",
             f"- Usage 미확인 시도: {missing_usage}. 전체 소비량: {summary['total_consumed_tokens'] if not missing_usage else '산출 불가'}",
             '', '| 슬롯 | 결과 | Requirement 수 | Gap 수 | Blocking Gap 수 | clarification_needed |',
             '| --- | --- | ---: | ---: | ---: | --- |']
    for slot in manifest['slots']:
        a = finals.get(slot)
        b = (a.get('response') or {}) if a else {}
        ok = a and a['code']=='success'
        lines.append(f"| {slot} | {a['error_type'] if a else '미실행'} | {len(b['requirements']) if ok else 'N/A'} | {len(b['gaps']) if ok else 'N/A'} | {sum(g['blocking'] for g in b['gaps']) if ok else 'N/A'} | {b.get('clarification_needed', 'N/A')} |")
    lines += ['', '## 근거', '', '- [전체 시도 및 원본 응답](attempts.jsonl)', '- [실행 조건 및 해시](manifest.json)', '- [집계 JSON](summary.json)', '',
              '실패 원인은 API 코드와 메시지만으로 분류했다. 중간 Stage 결과나 서버 로그를 사용하지 않았다. 원본 입력은 manifest에 보존했다. 성공 응답만의 의미 점수는 별도 사람 검토 후 확정한다.']
    (out/'report.md').write_text('\n'.join(lines)+'\n')


def self_test():
    seen = []
    it = iter(['rate_limit', 'gateway_error', 'success'])
    records = run_slot(lambda: {'code': next(it)}, seen.append)
    assert len(records)==3 and seen==[5,15]
    for code in ['structured_output_invalid', *STOP, 'empty_response', 'runner_transport_error']:
        assert len(run_slot(lambda: {'code': code}, seen.append))==1
    assert len(run_slot(lambda: {'code': 'timeout'}, lambda _: None))==3
    assert classify('structured_output_invalid', GAP_ERROR+'.')=='blocking_gap_missing'
    assert classify('structured_output_invalid', 'prefix '+GAP_ERROR)=='other_contract_unknown'
    assert classify('structured_output_invalid', SCHEMA_ERROR)== 'json_schema_indistinguishable'
    assert delay(1,'7')==7 and delay(2,'bad')==15
    assert len(cases())==12
    print('Offline checks passed: slot limits, retry exclusions, waits, response classification, frozen cases.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.run:
        parser.error('Use --run for billable evaluation or --self-test for offline checks.')
    sys.path.insert(0,str(ROOT/'backend'))
    env = environment()
    case_list = cases()
    eid = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = HERE/'runs'/eid
    out.mkdir(parents=True, exist_ok=False)
    manifest = {'evaluation_id': eid, 'gold_version':'1.0', 'started_at':now(), 'state':'running',
                'code_commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                'working_tree_status': subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True),
                'models': {'requirement_extraction':'gpt-5.6-luna','gap_analysis':'gpt-5.6-luna'},
                'reasoning':'model default', 'provider':'snowchat',
                'base_url':env.get('SNOWCHAT_BASE_URL') or 'https://factchat-cloud.mindlogic.ai/v1/gateway',
                'retry_policy': {'codes': sorted(RETRY), 'max_retries':2,'wait_seconds':[5,15],'scope':'whole_analysis'},
                'cases':case_list, 'slots':[f"{c['id']}-{r}" for r in range(1,4) for c in case_list], 'files':{}}
    paths = list((ROOT/'backend/app').rglob('*.py')) + list((ROOT/'backend/app/prompts').glob('*.md'))
    paths += [ROOT/'backend/pyproject.toml', ROOT/'backend/uv.lock', HERE/'README.md', HERE/'scenarios-draft.md', Path(__file__).resolve()]
    for path in paths:
        rel=path.relative_to(ROOT)
        dest=out/'snapshot'/rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path,dest)
        manifest['files'][str(rel)] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_json(out/'manifest.json',manifest)
    attempts=[]
    server=None
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port=sock.getsockname()[1]
    origin=f'http://127.0.0.1:{port}'
    print(f'Evaluation {eid}; 36 sequential slots; provider=snowchat; model=gpt-5.6-luna',flush=True)
    try:
        server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port),'--log-level','critical'],cwd=ROOT/'backend',env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            if server.poll() is not None:
                raise RuntimeError('Evaluation API failed to start')
            try:
                with urlopen(origin+'/openapi.json',timeout=1):
                    break
            except (URLError, OSError):
                time.sleep(.1)
        else:
            raise RuntimeError('Evaluation API startup timed out')
        for repetition in range(1,4):
            for c in case_list:
                slot=f"{c['id']}-{repetition}"
                def call():
                    a=request(origin,c['text'],env.get('FACTCHAT_API_KEY',''))
                    a['slot_id']=slot
                    a['scenario_id']=c['id']
                    a['attempt']=1+sum(x['slot_id']==slot for x in attempts)
                    attempts.append(a)
                    with (out/'attempts.jsonl').open('a') as f:
                        f.write(json.dumps(a,ensure_ascii=False)+'\n')
                    print(f"{slot} attempt={a['attempt']} {a['code']} {a['latency_seconds']}s",flush=True)
                    return a
                run_slot(call)
                # Persist waits added after each response, without losing completed attempts on interruption.
                (out/'attempts.jsonl').write_text(''.join(json.dumps(a,ensure_ascii=False)+'\n' for a in attempts))
                if attempts[-1]['code'] in STOP:
                    manifest['state']='aborted_configuration'
                    return
                if attempts[-1]['code'] in {'runner_transport_error','evaluation_contract_failed'}:
                    manifest['state']='aborted_runner'
                    return
        manifest['state']='completed'
    except BaseException:
        manifest['state']='interrupted_or_runner_error'
        raise
    finally:
        manifest['ended_at']=now()
        write_json(out/'manifest.json',manifest)
        summarize(out,manifest,attempts)
        if server:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
        print(f'Artifacts: {out}',flush=True)


if __name__ == '__main__':
    main()
