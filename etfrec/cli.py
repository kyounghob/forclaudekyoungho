"""명령줄 인터페이스.

    python -m etfrec generate --out data/synthetic [--n 15000] [--seed 42] [--effect 1.0]
    python -m etfrec train --out runs/seed42 [--data data/synthetic] [--n 15000] [--no-neural] [--prereq-policy required]
    python -m etfrec train --out runs/v1 --catalog-version 1 --generator-version 1 --prereq-policy off   # 노트북 v1 세계 재현
    python -m etfrec train --out runs/historical_v2 --prereq-policy off   # 기존 v2의 선수 미적용 비교 재현
    python -m etfrec recommend --bundle runs/seed42 --user 1 [--k 5] [--algorithm RULE]
    python -m etfrec serve --bundle runs/seed42 [--host 127.0.0.1] [--port 8000] [--sources-dir data/sources] [--expose-learners]
    python -m etfrec demo [--n 3000]      # 작은 규모로 학습한 뒤 바로 서버를 띄운다
    read -rs ETFREC_PSEUDO_KEY && export ETFREC_PSEUDO_KEY     # 키는 화면에 보이지 않게 입력(명령줄에 쓰면 셸 기록에 남는다)
    python -m etfrec pseudonymize --profiles A.csv --log B.csv --id-col member_id --out DIR --mapping-out PATH
    python -m etfrec export-deid --bundle runs/seed42 --k 5 --out FILE.csv [--report FILE.json]
    read -rs KRX_OPEN_API_KEY && export KRX_OPEN_API_KEY      # (선택) 공공데이터포털은 DATA_GO_KR_KEY를 같은 방식으로
    python -m etfrec sources list|check|sync|stats [--out data/sources] [--krx-csv 내려받은.csv|.xlsx]
        [--krx-csv-date YYYYMMDD] [--date YYYYMMDD] [--no-cross-check]
    (인증키는 환경변수로만 받는다. 명령줄 인자나 'KEY=값 명령' 형식은 ps·셸 기록에 남는다. 스냅샷 폴더 기본값은 ETFREC_SOURCES_DIR, 없으면 data/sources)
    python -m etfrec ops simulate --ops-dir runs/ops_sim [--n 3000] [--weeks 8] [--start 3]   # 닫힌 고리 모의 운영
    python -m etfrec ops init --ops-dir runs/ops --bundle runs/seed42 [--epsilon 0.1]
    python -m etfrec ops run-week --ops-dir runs/ops --data DIR [--week W]   # 주 1회(예: cron 매주 월요일)
    python -m etfrec ops status|history|rollback|freeze|unfreeze|prune --ops-dir runs/ops
    python -m etfrec serve --ops-dir runs/ops [--bundle runs/seed42]   # /api/serve·/api/feedback로 탐색·노출 기록
    python -m etfrec serve --public --bundle runs/seed42 [--ops-dir runs/ops] [--db runs/web/etfrec.db] [--trust-proxy]
        [--cookies auto|secure|insecure] [--service-start YYYY-MM-DD]   # 실사용자 웹 서비스(초대 코드: 환경변수 ETFREC_INVITE_CODE)
    python -m etfrec web create-admin|reset-password|revoke-admin --username NAME [--db ...]   # 비밀번호: ETFREC_ADMIN_PASSWORD 또는 입력
    python -m etfrec web export-dataset --out runs/web/export [--db ...] [--bundle runs/seed42]   # 주간 작업 입력(끝난 주까지)
    python -m etfrec web backup --out runs/web/backup.db | stats [--db ...]
    python -m etfrec web pilot-report [--db ...] [--out results/pilot] [--bundle runs/seed42]   # 파일럿 지표·기법 비교
    python -m etfrec web bootstrap [--db ...] [--bundle runs/seed42] [--ops-dir runs/ops]   # 컨테이너 첫 실행 준비(멱등)
    python -m etfrec desktop [--tunnel auto|token|quick|none] [--port 8000]   # 내 컴퓨터를 파일럿 서버로(자동 재시작·백업·절전 방지)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .config import GuardrailConfig, TrainConfig
from .data import Dataset
from .util import get_logger, json_safe


def _day_arg(v: str) -> str:
    """argparse 형식 검사: 숫자 8자리의 실제 날짜(YYYYMMDD)만 받는다."""
    from .sources.sync import parse_day
    try:
        return parse_day(v)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from None


def cmd_sources(a):
    from .sources import SOURCES, default_dir, load_etf_universe, public_info, sync_all, type_stats
    from .sources.sync import check_sources
    a.out = a.out or default_dir()
    if a.action == "list":
        for k, v in SOURCES.items():
            print(f"- {k}: {v['name']} | {v['url'] or '-'} | {v['menu']} | 접근: {v['access']} | 확인: {v['verified']}")
    elif a.action == "check":                                  # 출처 루트마다 HEAD 1회
        for r in check_sources():
            print(f"{r['status']:40s} {r['name']}  {r['url']}")
    elif a.action == "sync":
        prov = sync_all(a.out, bas_dt=a.date, krx_csv=a.krx_csv, krx_csv_date=a.krx_csv_date, cross_check=not a.no_cross_check)
        print(json.dumps(prov, ensure_ascii=False, indent=2))                   # 오류 문구의 인증키 값은 sync가 가린 뒤 기록한다
        print(f"스냅샷 폴더: {os.path.abspath(a.out)} (서버는 시작할 때 한 번 읽으므로 실행 중인 서버는 다시 시작하세요)", file=sys.stderr)
    elif a.action == "stats":
        df, prov = load_etf_universe(a.out)
        print(public_info(prov)["label"], "| rows", len(df))
        for t in type_stats(df):
            px = (f"  괴리율 절댓값 중앙값 {t['premium_abs_median'] * 100:.2f}%" if t["premium_abs_median"] is not None else "") + \
                 (f"  거래량 중앙값 {t['volume_median']:,}" if t["volume_median"] is not None else "")
            print(f"{t['name']:16s} {t['count']:4d}개  환헤지 {t['hedged']:3d}  총보수 중앙값 {t['fee_median']}{px}  예시 {t['examples']}")


def cmd_generate(a):
    cfg = TrainConfig(n_learners=a.n, seed=a.seed, effect_scale=a.effect, catalog_version=a.catalog_version, generator_version=a.generator_version)
    ds = Dataset.synthetic(cfg)
    ds.save_csv(a.out)
    print(json.dumps(ds.summary(), ensure_ascii=False, indent=2))
    print("저장:", os.path.abspath(a.out))


def cmd_train(a):
    from .pipeline import train
    cfg = TrainConfig(n_learners=a.n, seed=a.seed, effect_scale=a.effect, catalog_version=a.catalog_version, generator_version=a.generator_version,
                      guardrail=GuardrailConfig(prereq_block=a.prereq_policy == "required"), operational_policy=a.operational_policy)
    ds = Dataset.from_csv(a.data) if a.data else Dataset.synthetic(cfg)
    if a.data:
        print("학습 데이터:", os.path.abspath(a.data), "(경로는 터미널에만 표시하고 번들에는 'csv'로 기록)")
    bundle = train(ds, cfg, out_dir=a.out, enable_neural=not a.no_neural)
    if bundle.selection.get("operational_policy") == "PurposeStageRule":
        print("운영 정책: 목적 단계 규칙(선언된 고정식; 역사적 설정 탐색과 별도)")
    else:
        print("운영 설정:", bundle.algos[bundle.selection["operational_algorithm"]].name)


def cmd_recommend(a):
    from .pipeline import Bundle
    from .service import RecommendationService
    svc = RecommendationService(Bundle.load(a.bundle), allow_any_config=True)     # 로컬 개발 도구라 임의 설정 번호도 받는다
    algorithm = int(a.algorithm) if a.algorithm and a.algorithm.isdigit() else a.algorithm
    out = svc.recommend(a.user, k=a.k, algorithm=algorithm)
    print(json.dumps(json_safe({k: v for k, v in out.items() if k != "topic_map"}), ensure_ascii=False, indent=2))


LOOPBACK = ("127.0.0.1", "localhost", "::1")


def _web_config(a, local: bool):
    """serve --public: 실사용자 계정·학습자 화면 설정. Secure 쿠키는 HTTPS 프록시 뒤(--trust-proxy)이거나 외부 주소로 열 때 기본으로 켠다."""
    from .web.app import WebConfig
    cookies = getattr(a, "cookies", "auto")
    secure = cookies == "secure" or (cookies == "auto" and (a.trust_proxy or not local))
    return WebConfig(db_path=a.db, public=True, invite_code=os.environ.get("ETFREC_INVITE_CODE") or None, secure_cookies=secure,
                     trust_proxy=a.trust_proxy, service_start=a.service_start)


def _registry_bundle(ops_dir: str):
    """운영 등록부가 가리키는 서빙 번들(없으면 기준 번들) 폴더."""
    from .ops.registry import PolicyRegistry
    st = PolicyRegistry(ops_dir).state
    b = st.get("serving_bundle") or st.get("base_bundle")
    if b and os.path.basename(b) == "bundle.pkl":
        b = os.path.dirname(b)
    return b


def cmd_serve(a):
    import uvicorn
    from .api import create_app
    local = a.host in LOOPBACK
    public = getattr(a, "public", False)
    expose = (local or getattr(a, "expose_learners", False)) and not public   # 학습자 단위 조회는 학습 환경 안(로컬)에서만 기본으로 켠다
    ops_dir = getattr(a, "ops_dir", None)
    if not a.bundle:
        if not ops_dir:
            sys.exit("--bundle 또는 --ops-dir가 필요합니다")
        a.bundle = _registry_bundle(ops_dir)
        if not a.bundle:
            sys.exit("운영 등록부에 서빙 번들이 없습니다. --bundle을 주세요")
    web = _web_config(a, local) if public else None
    try:
        app = create_app(a.bundle, designs_dir=a.designs, sources_dir=getattr(a, "sources_dir", None), expose_learners=expose,
                         ops_dir=ops_dir, web=web)
    except ValueError as e:                                        # 예: 이미 정해진 서비스 시작일과 다른 --service-start
        sys.exit(f"서버를 시작하지 못했습니다: {e}")
    if public:
        st = app.state.web_store.stats()
        print(f"공개 모드: 학습자 화면 /, 스튜디오 /studio(관리자만) · 계정 DB {a.db} · 가입 {'초대 코드 필요' if web.invite_code else '누구나'}"
              f" · 쿠키 {'Secure(HTTPS 전용)' if web.secure_cookies else '일반(HTTP 시험용)'} · 운영 루프 {'켜짐' if ops_dir else '꺼짐'}")
        if not st["admins"]:
            print(f"관리자 계정이 없습니다. 만들기: python -m etfrec web create-admin --db {a.db} --username admin", file=sys.stderr)
        if web.secure_cookies and not a.trust_proxy:
            print("주의: Secure 쿠키는 HTTPS 주소에서만 저장됩니다. HTTPS 없이 평문 HTTP로 시험하려면 --cookies insecure", file=sys.stderr)
    elif not local:
        print(f"주의: {a.host}로 열면 같은 망의 누구나 접근할 수 있습니다. 서빙 API에는 인증이 없습니다. "
              f"기준 학습자 조회는 {'켜짐(--expose-learners)' if expose else '꺼짐(--expose-learners로만 켬)'}.", file=sys.stderr)
    print(f"http://{a.host}:{a.port}  (번들 {a.bundle})")
    uvicorn.run(app, host=a.host, port=a.port, log_level="info", server_header=not public)     # 공개 모드는 서버 종류를 알리지 않는다


def cmd_demo(a):
    from .pipeline import train
    out = a.out
    if not os.path.exists(os.path.join(out, "bundle.pkl")):
        cfg = TrainConfig(n_learners=a.n, guardrail=GuardrailConfig(prereq_block=a.prereq_policy == "required"), operational_policy=a.operational_policy)
        train(Dataset.synthetic(cfg), cfg, out_dir=out, enable_neural=not a.no_neural)
    else:
        from .pipeline import Bundle
        existing = Bundle.load(out)
        if bool(existing.config.guardrail.prereq_block) != (a.prereq_policy == "required"):
            sys.exit("기존 demo 번들의 선수 정책이 --prereq-policy와 다릅니다. 다른 --out 폴더를 지정하거나 train으로 다시 학습하세요")
        if getattr(existing.config, "operational_policy", "PurposeStageRule") != a.operational_policy:
            sys.exit("기존 demo 번들의 운영 정책이 --operational-policy와 다릅니다. 다른 --out 폴더를 지정하거나 train으로 다시 학습하세요")
    a.bundle = out; a.designs = None; a.sources_dir = None; a.expose_learners = False
    cmd_serve(a)


def _paths_overlap(a: str, b: str) -> bool:
    """두 폴더가 같거나 한쪽이 다른 쪽 안에 있는지. 실제 경로(심볼릭 링크 해석)·대소문자 정규화로 비교하고, 이미 있는 폴더는
    os.path.samefile로도 확인한다(대소문자 무시 파일시스템에서 철자만 다른 경로)."""
    ra, rb = (os.path.normcase(os.path.realpath(x)) for x in (a, b))
    if os.path.commonpath([ra, rb]) in (ra, rb):
        return True
    def ancestors(p):
        p = os.path.realpath(p)
        while True:
            yield p
            q = os.path.dirname(p)
            if q == p:
                return
            p = q
    for x, y in ((a, b), (b, a)):
        if os.path.exists(y):
            for anc in ancestors(x):
                if os.path.exists(anc) and os.path.samefile(anc, y):
                    return True
    return False


def cmd_pseudonymize(a):
    """운영 원본 → 가명 학습 입력(profiles.csv·study_log.csv). 키는 환경변수에서만 읽고, 매핑표는 --mapping-out에만 쓴다."""
    import pandas as pd
    from .privacy import KEY_ENV, MIN_KEY_LENGTH, build_pseudonymized_inputs
    key = os.environ.get(KEY_ENV, "")
    if len(key) < MIN_KEY_LENGTH:
        sys.exit(f"{KEY_ENV} 환경변수에 {MIN_KEY_LENGTH}자 이상의 가명처리 키가 없어 실행하지 않습니다(키는 명령줄 인자로 받지 않음)")
    out, mp = os.path.abspath(a.out), os.path.abspath(a.mapping_out)
    if _paths_overlap(out, os.path.dirname(mp)):
        sys.exit("매핑표(--mapping-out)는 학습 입력 폴더(--out) 밖, 학습 환경과 분리된 곳에 두어야 합니다"
                 "(심볼릭 링크·대소문자만 다른 경로도 같은 폴더로 봅니다)")
    raw_p = pd.read_csv(a.profiles, dtype={a.id_col: str})
    raw_l = pd.read_csv(a.log, dtype={a.id_col: str})
    try:
        profiles, log, mapping = build_pseudonymized_inputs(raw_p, raw_l, a.id_col, key)
    except ValueError as e:
        sys.exit(f"가명처리 실패: {e}")
    os.makedirs(out, exist_ok=True)
    profiles.to_csv(os.path.join(out, "profiles.csv"), index=False, encoding="utf-8-sig")
    log.to_csv(os.path.join(out, "study_log.csv"), index=False, encoding="utf-8-sig")
    os.makedirs(os.path.dirname(mp), exist_ok=True)
    mapping.to_csv(mp, index=False, encoding="utf-8-sig")
    print(json.dumps(dict(users=len(profiles), log_rows=len(log), raw_log_rows=len(raw_l),
                          events_merged_into_attempts=len(raw_l) - len(log) if "session_id" in raw_l.columns else None,
                          training_input=out, mapping=mp,
                          dropped_profile_columns=sorted(set(raw_p.columns) - set(profiles.columns)),
                          dropped_log_columns=sorted(set(raw_l.columns) - set(log.columns)),
                          note="day·minute는 0(시각 제거), hour는 4개 시간대. 원시 연령·연소득은 학습 입력에만 있고 번들에는 남지 않습니다"),
                     ensure_ascii=False, indent=2))


def cmd_export_deid(a):
    """번들의 저장 프로필 → k-익명 학습자 표(CSV)와 보고서(JSON). k를 만족하지 못하면 파일을 쓰지 않는다."""
    from .pipeline import Bundle
    from .privacy import export_deid
    try:
        table, report = export_deid(Bundle.load(a.bundle), k=a.k)
    except ValueError as e:
        sys.exit(f"반출 실패: {e}")
    if not (report["satisfied"] and report["verified"]):
        sys.exit(f"k={a.k}를 만족하는 표를 만들지 못해 파일을 쓰지 않았습니다")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    table.to_csv(a.out, index=False, encoding="utf-8-sig")
    rp = a.report or os.path.splitext(a.out)[0] + "_report.json"
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(json_safe(report), f, ensure_ascii=False, indent=2)
    print(f"k={a.k} 충족: {report['rows_out']}행(입력 {report['rows_in']}행, 일반화 {len(report['generalized'])}단계, "
          f"국소 억제 {report['suppressed_rows']}행, 삭제 {report['removed_rows']}행, 최소 셀 {report['final_min_group']}명) → {a.out} · 보고서 {rp}")


def cmd_ops(a):
    try:
        _cmd_ops(a)
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as e:      # 예상된 거절(같은 주 재판정·잠금·자료 부족)은 한 줄로
        sys.exit(f"운영 루프: {e}")


def _cmd_ops(a):
    from .ops.exploration import ExplorationConfig
    from .ops.loop import LoopConfig, default_settings, run_week, simulate
    from .ops.logstore import OpsLog
    from .ops.policies import declared_spec, public_spec
    from .ops.registry import PolicyRegistry
    act = a.ops_cmd
    if act == "simulate":
        cfg = LoopConfig(exploration=ExplorationConfig(epsilon=a.epsilon, method=a.method), refresh_serving=False,
                         include_zoo=not a.no_zoo)
        s = simulate(a.ops_dir, n=a.n, weeks=a.weeks, start=a.start, seed=a.seed, cfg=cfg, force=a.force)
        print(f"{'주':>3} {'결정':<14} {'탐색/노출':>10} {'OPE 현재':>9} {'실제 현재':>9}  판정 뒤 정책")
        for r in s["weeks"]:
            f = lambda v: f"{v:.4f}" if isinstance(v, float) else "–"
            print(f"{r['week']:>3} {r['event']:<14} {r['explored']:>4}/{r['impressions']:<5} {f(r['ope_champion']):>9} {f(r['true_champion']):>9}  {r['champion_after']}"
                  + (f"   (미통과: {', '.join(r['failed'])})" if r.get('failed') else ""))
        print(f"이력 해시 사슬: {'정상' if s['history_ok'] else '손상'} · 보고서: {os.path.join(a.ops_dir, 'reports')}")
        return
    if act == "init":
        cfg = LoopConfig(exploration=ExplorationConfig(epsilon=a.epsilon, method=a.method, temperature=a.temperature))
        reg = PolicyRegistry.init(a.ops_dir, declared_spec(), default_settings(cfg), base_bundle=os.path.abspath(a.bundle),
                                  note=a.note or "", force=a.force)
        print(f"운영 등록부 생성: {reg.path} · 현재 정책 {reg.champion['name']} ({reg.champion['version']})")
        return
    reg = PolicyRegistry(a.ops_dir)
    if act == "run-week":
        from .data import Dataset
        ds = Dataset.from_csv(a.data)
        week = a.week if a.week is not None else int(ds.log.week.max())
        cfg = LoopConfig.from_settings(reg.settings, refresh_serving=not a.no_serving, full_retrain=a.full_retrain)
        r = run_week(a.ops_dir, ds, week, cfg, force=a.force)
        print(f"{week}주 결정: {r['event']} — {r.get('reason', '')}\n보고서: {r['report']}")
    elif act == "status":
        ch = reg.champion; log = OpsLog(os.path.join(a.ops_dir, "logs")); weeks = log.weeks()
        print(json.dumps(dict(champion=public_spec(ch), adopted_week=ch.get("adopted_week"), frozen=reg.frozen,
                              freeze_reason=reg.state.get("freeze_reason"), last_change_week=reg.state.get("last_change_week"),
                              serving_bundle=reg.state.get("serving_bundle"), exploration=reg.settings.get("exploration"),
                              latest_log=log.counts(weeks[-1]) if weeks else None, history=reg.verify()), ensure_ascii=False, indent=2))
    elif act == "history":
        if a.verify:
            v = reg.verify(); print(f"해시 사슬 {'정상' if v['ok'] else '손상(seq ' + str(v['first_bad_seq']) + ')'} · {v['records']}건")
            if not v["ok"]:
                sys.exit(1)
        for h in reg.history()[-a.limit:]:
            print(f"#{h['seq']:<3} {h['ts']} {h.get('week') if h.get('week') is not None else '-':>3}주 {h['event']:<15} "
                  f"{(h.get('champion_after') or {}).get('name', '')}  {h.get('reason') or ''}")
    elif act == "rollback":
        r = reg.rollback(None, a.reason, manual=True)
        print(f"되돌림: {r['champion_before']['name']} → {r['champion_after']['name']}")
    elif act in ("freeze", "unfreeze"):
        reg.set_frozen(act == "freeze", a.reason)
        print(f"{'동결' if act == 'freeze' else '동결 해제'}: {a.reason}")
    elif act == "prune":
        removed = OpsLog(os.path.join(a.ops_dir, "logs")).prune(a.keep_weeks)
        reg.append_history(dict(event="pruned", week=None, reason=f"최근 {a.keep_weeks}주만 보존", removed=removed))
        print(f"삭제 {len(removed)}개: {removed}")


def _admin_password() -> str:
    """관리자 비밀번호: 환경변수 ETFREC_ADMIN_PASSWORD 또는 터미널 입력(명령줄 인자는 ps·셸 기록에 남아 받지 않는다)."""
    pw = os.environ.get("ETFREC_ADMIN_PASSWORD")
    if pw:
        return pw
    import getpass
    if not sys.stdin.isatty():
        raise ValueError("비밀번호는 환경변수 ETFREC_ADMIN_PASSWORD나 터미널 입력으로만 받습니다")
    pw = getpass.getpass("비밀번호(8자 이상): ")
    if pw != getpass.getpass("비밀번호 확인: "):
        raise ValueError("비밀번호 확인이 다릅니다")
    return pw


def cmd_web(a):
    try:
        _cmd_web(a)
    except (FileExistsError, KeyError, ValueError) as e:
        sys.exit(f"웹 계정: {e.args[0] if e.args else e}")


def _memory_limit():
    """컨테이너 메모리 한도(바이트, cgroup v2·v1). 한도가 없거나 읽을 수 없으면 None."""
    for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            v = open(path).read().strip()
        except OSError:
            continue
        if v.isdigit() and int(v) < 1 << 50:                       # v1의 '한도 없음'은 아주 큰 수로 나온다
            return int(v)
    return None


def _bootstrap_scale(n=None, limit=None) -> tuple:
    """첫 실행 학습 규모(학습자 수, 병렬 작업 수, 이유). 측정한 최대 메모리: 15,000명·작업 1개 약 1.1GB, 3,000명 약 0.34GB."""
    if n:
        return int(n), (1 if limit and limit < 3 * 2 ** 30 else TrainConfig().n_workers), "지정한 규모"
    gib = None if limit is None else limit / 2 ** 30
    if gib is None or gib >= 3:
        return TrainConfig().n_learners, TrainConfig().n_workers, "메모리 한도 없음 또는 3GB 이상"
    if gib >= 1.5:
        return TrainConfig().n_learners, 1, f"메모리 한도 {gib:.1f}GB: 병렬 작업 1개"
    return 3000, 1, f"메모리 한도 {gib:.1f}GB라 학습자 3,000명으로 축소, 보고서 번들은 15,000명"


def _web_bootstrap(a, store, admin_hint: bool = True):
    """컨테이너 첫 실행 준비(여러 번 실행해도 안전): 번들이 없으면 학습 → 운영 등록부가 없으면 생성 →
    ETFREC_ADMIN_PASSWORD가 있고 그 계정(ETFREC_ADMIN_USERNAME, 기본 admin)이 없으면 관리자 생성."""
    if not os.path.exists(os.path.join(a.bundle, "bundle.pkl")):
        from .pipeline import train
        n, workers, why = _bootstrap_scale(a.n or os.environ.get("ETFREC_BOOTSTRAP_N"), _memory_limit())
        print(f"번들이 없어 학습합니다: 모의 학습자 {n:,}명, 병렬 작업 {workers}개, 신경망 없이({why}) → {a.bundle}", flush=True)
        cfg = TrainConfig(n_learners=n, n_workers=workers)
        train(Dataset.synthetic(cfg), cfg, out_dir=a.bundle, enable_neural=False)
    if a.ops_dir and not os.path.exists(os.path.join(a.ops_dir, "registry.json")):
        from .ops.loop import LoopConfig, default_settings
        from .ops.policies import declared_spec
        from .ops.registry import PolicyRegistry
        PolicyRegistry.init(a.ops_dir, declared_spec(), default_settings(LoopConfig()), base_bundle=os.path.abspath(a.bundle),
                            note="첫 실행 자동 준비")
        print(f"운영 등록부를 만들었습니다: {a.ops_dir}")
    name, pw = os.environ.get("ETFREC_ADMIN_USERNAME", "").strip() or "admin", os.environ.get("ETFREC_ADMIN_PASSWORD", "")
    if pw:
        u = store.user_by_name(name)
        if u is None:
            store.create_user(name, pw, consent_version="admin-env", is_admin=True)
            print(f"관리자 계정을 만들었습니다: {name}")
        elif not u["is_admin"]:
            print(f"경고: {name}은 일반 학습자 계정이라 관리자 권한을 자동으로 주지 않습니다(web create-admin으로 직접 부여)", file=sys.stderr)
    if admin_hint and not store.stats()["admins"]:
        print("관리자 계정이 없습니다. 환경변수 ETFREC_ADMIN_PASSWORD(아이디는 ETFREC_ADMIN_USERNAME, 기본 admin)를 넣고 다시 시작하면 만듭니다",
              file=sys.stderr)


def _desktop_bootstrap(a, store):
    """데스크탑 첫 실행: 공통 준비 뒤 관리자 계정이 없으면 이 창에서 입력받아 만든다."""
    _web_bootstrap(a, store, admin_hint=False)
    if store.stats()["admins"]:
        return
    if a.no_prompt or not sys.stdin.isatty():
        print("관리자 계정이 없습니다. 이 창에서 직접 실행하거나 python -m etfrec web create-admin --username admin으로 만드세요", file=sys.stderr)
        return
    print("관리자 계정을 만듭니다. 관리자 메뉴에서 파일럿 보고서와 분석 자료를 받습니다.")
    name = input("관리자 아이디 [admin]: ").strip() or "admin"
    store.create_user(name, _admin_password(), consent_version="admin-desktop", is_admin=True)
    print(f"관리자 계정을 만들었습니다: {name}")


def cmd_desktop(a):
    from .desktop import run_desktop
    from .web.store import WebStore
    try:
        sys.exit(run_desktop(a, WebStore, _desktop_bootstrap))
    except (FileExistsError, KeyError, ValueError) as e:
        sys.exit(f"데스크탑 운영: {e.args[0] if e.args else e}")


def _cmd_web(a):
    from datetime import date
    from .web.store import WebStore
    store = WebStore(a.db)
    act = a.web_cmd
    if act == "create-admin":
        if store.user_by_name(a.username):
            store.set_admin(a.username, True)
            print(f"기존 계정 {a.username}에 관리자 권한을 주었습니다(비밀번호는 그대로)")
        else:
            store.create_user(a.username, _admin_password(), consent_version="admin-cli", is_admin=True)
            print(f"관리자 계정을 만들었습니다: {a.username} · 로그인: /?admin=1 → 스튜디오 /studio")
    elif act == "reset-password":
        store.set_password(a.username, _admin_password())
        print(f"{a.username} 비밀번호를 바꾸고 기존 로그인을 모두 끊었습니다")
    elif act == "revoke-admin":
        store.set_admin(a.username, False)
        print(f"{a.username}의 관리자 권한을 거두었습니다")
    elif act == "backup":
        store.backup(a.out)
        print(f"백업: {os.path.abspath(a.out)} (계정·학습 기록 DB 사본. 운영 기록·번들은 --ops-dir 폴더를 따로 보관)")
    elif act == "bootstrap":
        _web_bootstrap(a, store)
    elif act == "pilot-report":
        from .web.pilot import pilot_report, write_report
        svc = None
        if not a.no_compare:
            bundle = a.bundle or (_registry_bundle(a.ops_dir) if os.path.exists(os.path.join(a.ops_dir, "registry.json")) else None)
            if bundle:
                from .pipeline import Bundle
                from .service import RecommendationService
                svc = RecommendationService(Bundle.load(bundle))
        now = None
        if a.as_of:
            from datetime import datetime as _dt
            now = _dt.fromisoformat(a.as_of + "T23:59:59").timestamp()           # 그날 끝까지의 기록으로 분석
        rep = pilot_report(store, svc=svc, window_days=a.window_days, k=a.k, now=now)
        paths = write_report(rep, a.out)
        rate = rep["primary"]["rate"]
        print(f"참가자 {rep['participants']}명(7일 관측 완료 {rep['eligible_7d']}명) · 주 지표 7일 통과율 "
              f"{'–' if rate is None else format(rate * 100, '.1f') + '%'} → {paths['markdown']}")
    elif act == "stats":
        st = store.stats()
        st.update(service_start=store.meta("service_start"))
        print(json.dumps(json_safe(st), ensure_ascii=False, indent=2))
    elif act == "export-dataset":
        start = store.meta("service_start")
        if start is None:
            raise ValueError("서비스 시작일이 아직 없습니다(serve --public을 한 번 실행하면 정해집니다)")
        start = date.fromisoformat(start)
        profiles, log = store.export_dataset(start)
        current = (date.today() - start).days // 7
        if not a.include_current_week:                            # 진행 중인 주는 빼서 주간 작업이 끝난 주만 판정하게 한다
            log = log[log.week < current]
        if profiles.empty or log.empty:
            raise ValueError(f"내보낼 학습 기록이 없습니다(현재 {current}주차, 끝난 주의 기록만 내보냄)")
        from .catalog import Catalog
        catalog = None
        if a.bundle:
            from .pipeline import Bundle
            catalog = Bundle.load(a.bundle).catalog
        ds = Dataset(profiles, log.reset_index(drop=True), catalog or Catalog.default(), source="web",
                     meta=dict(service_start=start.isoformat(), current_week=current, included_current_week=bool(a.include_current_week)))
        ds.save_csv(a.out)
        diag = int((ds.log["source"] == "diagnosis").sum())
        print(f"내보냄: 학습자 {len(profiles)}명 · 기록 {len(ds.log)}행(진단 인정 {diag}행) · {int(ds.log.week.min())}~{int(ds.log.week.max())}주 → "
              f"{os.path.abspath(a.out)}\n다음: python -m etfrec ops run-week --ops-dir runs/ops --data {a.out}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="etfrec", description="ETF 교육 콘텐츠 개인화·세그먼트 추천 시스템")
    sub = p.add_subparsers(dest="cmd", required=True)
    def versions(parser):
        parser.add_argument("--catalog-version", type=int, default=TrainConfig().catalog_version, help="1 = 노트북 원본 주제 20 × 수준 3 = 60단원, 2 = 주제 22 × 수준 3 = 66단원 + 선수 관계")
        parser.add_argument("--generator-version", type=int, default=TrainConfig().generator_version, help="1 = 노트북 난수 순서, 2 = 목적·선수 관계 반영")
    g = sub.add_parser("generate", help="모의 데이터 생성 → CSV"); g.add_argument("--out", required=True)
    g.add_argument("--n", type=int, default=TrainConfig().n_learners); g.add_argument("--seed", type=int, default=TrainConfig().seed)
    g.add_argument("--effect", type=float, default=TrainConfig().effect_scale); versions(g); g.set_defaults(fn=cmd_generate)
    t = sub.add_parser("train", help="학습 → 검증 → 선택 → 테스트 → 번들 저장"); t.add_argument("--out", required=True)
    t.add_argument("--data", default=None, help="profiles.csv·study_log.csv·catalog.csv가 있는 폴더(없으면 모의 데이터)")
    t.add_argument("--n", type=int, default=TrainConfig().n_learners); t.add_argument("--seed", type=int, default=TrainConfig().seed)
    t.add_argument("--effect", type=float, default=TrainConfig().effect_scale); t.add_argument("--no-neural", action="store_true")
    t.add_argument("--prereq-policy", choices=("required", "off"), default="required",
                   help="선수 정책: required(기본)는 선택·평가에도 선수 조건 적용, off는 기존 v1/v2의 미적용 비교 재현용")
    t.add_argument("--operational-policy", choices=("PurposeStageRule", "legacy"), default="PurposeStageRule",
                   help="기본은 목적·로드맵 고정 운영 규칙. legacy는 과거 라우터 선정 재현용")
    versions(t); t.set_defaults(fn=cmd_train)
    so = sub.add_parser("sources", help="공개 데이터 출처 목록·접근 점검·스냅샷 동기화·유형 통계")
    so.add_argument("action", choices=["list", "check", "sync", "stats"])
    so.add_argument("--out", default=None, help="스냅샷 폴더(기본: 환경변수 ETFREC_SOURCES_DIR, 없으면 data/sources — 서버와 같은 규칙)")
    so.add_argument("--date", default=None, type=_day_arg, help="API 기준일 YYYYMMDD(기본: 직전 평일. 휴장일·미공개면 응답 0행 → empty로 기록)")
    so.add_argument("--krx-csv", default=None, help="KRX 정보데이터시스템에서 직접 내려받은 'ETF 전종목 기본정보' 파일(CSV, 또는 openpyxl·xlrd 설치 시 Excel). 화면 자동 호출은 하지 않음")
    so.add_argument("--krx-csv-date", default=None, type=_day_arg, help="내려받은 파일의 기준일 YYYYMMDD(없으면 파일 수정일을 '내려받은 날'로 기록)")
    so.add_argument("--no-cross-check", action="store_true", help="공공데이터포털 KRX상장종목정보로 단축코드·ISIN을 교차 확인하지 않음")
    so.set_defaults(fn=cmd_sources)          # 인증키는 환경변수 KRX_OPEN_API_KEY·DATA_GO_KR_KEY로만(명령줄 인자는 ps·셸 기록에 남음)
    r = sub.add_parser("recommend", help="번들로 한 학습자 추천"); r.add_argument("--bundle", required=True)
    r.add_argument("--user", type=int, required=True); r.add_argument("--k", type=int, default=5); r.add_argument("--algorithm", default=None)
    r.set_defaults(fn=cmd_recommend)
    s = sub.add_parser("serve", help="API + UI 서버"); s.add_argument("--bundle", default=None)
    s.add_argument("--ops-dir", default=None, help="운영 루프 폴더: 현재 운영 정책으로 /api/serve(탐색·노출 기록)·/api/feedback 사용")
    s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8000); s.add_argument("--designs", default=None)
    s.add_argument("--sources-dir", default=None, help="공개 데이터 스냅샷 폴더(기본: ETFREC_SOURCES_DIR, 없으면 data/sources)")
    s.add_argument("--expose-learners", action="store_true",
                   help="로컬 주소가 아닌 --host로 열 때도 기준 학습자 조회(/api/learners)를 켠다(학습 환경 안에서만 쓸 것)"); s.set_defaults(fn=cmd_serve)
    web_db = os.environ.get("ETFREC_WEB_DB", "runs/web/etfrec.db")
    s.add_argument("--public", action="store_true",
                   help="실사용자 웹 서비스: 가입·로그인 학습자 화면이 첫 화면(/), 스튜디오(/studio)·운영·평가 API는 관리자만")
    s.add_argument("--db", default=web_db, help=f"학습자 계정·기록 DB(SQLite, 기본 ETFREC_WEB_DB 또는 {web_db})")
    s.add_argument("--cookies", choices=("auto", "secure", "insecure"), default="auto",
                   help="로그인 쿠키 Secure 속성: auto는 --trust-proxy이거나 외부 주소일 때 Secure(HTTPS 전용)")
    s.add_argument("--trust-proxy", action="store_true", help="HTTPS 리버스 프록시 뒤: X-Forwarded-For로 요청 IP를 판단(속도 제한)")
    s.add_argument("--service-start", default=None, help="주차 기준일 YYYY-MM-DD(처음 한 번만 저장, 기본: 첫 실행 주의 월요일)")
    d = sub.add_parser("demo", help="작은 규모 학습 후 바로 서버 실행"); d.add_argument("--n", type=int, default=3000)
    d.add_argument("--out", default="artifacts/demo_bundle"); d.add_argument("--host", default="127.0.0.1"); d.add_argument("--port", type=int, default=8000)
    d.add_argument("--no-neural", action="store_true"); d.set_defaults(fn=cmd_demo)
    d.add_argument("--prereq-policy", choices=("required", "off"), default="required",
                   help="선수 정책: required(기본), off(역사적 미적용 비교 재현용); 기존 번들의 정책이 다르면 재학습 필요")
    d.add_argument("--operational-policy", choices=("PurposeStageRule", "legacy"), default="PurposeStageRule")
    ps = sub.add_parser("pseudonymize", help="운영 원본(외부 회원 ID) → 가명 학습 입력 + 별도 매핑표 (키: 환경변수 ETFREC_PSEUDO_KEY)")
    ps.add_argument("--profiles", required=True, help="외부 ID 열이 있는 프로필 CSV"); ps.add_argument("--log", required=True, help="외부 ID 열이 있는 학습 로그 CSV")
    ps.add_argument("--id-col", required=True, help="외부 회원 ID 열 이름"); ps.add_argument("--out", required=True, help="학습 입력 폴더(profiles.csv·study_log.csv)")
    ps.add_argument("--mapping-out", required=True, help="매핑표 CSV 경로(학습 환경 밖, --out 안이면 거부)"); ps.set_defaults(fn=cmd_pseudonymize)
    ex = sub.add_parser("export-deid", help="번들 저장 프로필 → k-익명 학습자 표(일반화 → 국소 억제) + 보고서")
    ex.add_argument("--bundle", required=True); ex.add_argument("--k", type=int, default=5); ex.add_argument("--out", required=True)
    ex.add_argument("--report", default=None, help="보고서 JSON 경로(기본: --out 이름 + _report.json)"); ex.set_defaults(fn=cmd_export_deid)
    o = sub.add_parser("ops", help="자동 운영 루프: 탐색 기록·주간 재학습/재선정·검증 게이트·교체 이력")
    osub = o.add_subparsers(dest="ops_cmd", required=True)
    def ops_dir(parser, default="runs/ops"):
        parser.add_argument("--ops-dir", default=default, help=f"운영 기록 폴더(기본 {default})")
    oi = osub.add_parser("init", help="등록부 생성(현재 정책 = 선언 정책 PurposeStageRule)"); ops_dir(oi)
    oi.add_argument("--bundle", required=True, help="기준 번들(후보 설정·신호 설명을 읽는다)")
    oi.add_argument("--epsilon", type=float, default=0.1); oi.add_argument("--method", choices=("uniform", "softmax"), default="uniform")
    oi.add_argument("--temperature", type=float, default=0.5); oi.add_argument("--note", default=None)
    oi.add_argument("--force", action="store_true", help="기존 등록부를 .bak로 옮기고 새로 만든다")
    ow = osub.add_parser("run-week", help="주간 작업: 재학습·재선정·게이트·결정·이력"); ops_dir(ow)
    ow.add_argument("--data", required=True, help="profiles.csv·study_log.csv(·catalog.csv) 폴더. 결정할 주까지의 기록")
    ow.add_argument("--week", type=int, default=None, help="결정할 주(기본: 기록의 마지막 주)")
    ow.add_argument("--force", action="store_true", help="이미 결정한 주를 다시 판정")
    ow.add_argument("--full-retrain", action="store_true", help="전체 학습 파이프라인으로 기준 번들도 새로 학습(느림)")
    ow.add_argument("--no-serving", action="store_true", help="다음 주 서빙 번들을 만들지 않는다")
    om = osub.add_parser("simulate", help="합성 세계에서 서빙→반응→주간 작업을 반복"); ops_dir(om, "runs/ops_sim")
    om.add_argument("--n", type=int, default=3000); om.add_argument("--weeks", type=int, default=8)
    om.add_argument("--start", type=int, default=3); om.add_argument("--seed", type=int, default=TrainConfig().seed)
    om.add_argument("--epsilon", type=float, default=0.1); om.add_argument("--method", choices=("uniform", "softmax"), default="uniform")
    om.add_argument("--no-zoo", action="store_true", help="기존 설정은 후보에서 빼고 가중치 변형만 비교")
    om.add_argument("--force", action="store_true", help="폴더가 있으면 지우고 새로 시작")
    for name, hp in (("status", "현재 정책·동결·최근 기록"), ("history", "교체 이력"), ("rollback", "직전 정책으로 수동 되돌림"),
                     ("freeze", "자동 교체 동결"), ("unfreeze", "동결 해제"), ("prune", "오래된 노출·반응 기록 삭제")):
        q = osub.add_parser(name, help=hp); ops_dir(q)
        if name == "history":
            q.add_argument("--limit", type=int, default=20); q.add_argument("--verify", action="store_true", help="해시 사슬 검사")
        if name in ("rollback", "freeze", "unfreeze"):
            q.add_argument("--reason", required=True)
        if name == "prune":
            q.add_argument("--keep-weeks", type=int, required=True)
    o.set_defaults(fn=cmd_ops)
    w = sub.add_parser("web", help="실사용자 웹 서비스 관리: 관리자 계정·비밀번호·학습 데이터 내보내기·통계")
    wsub = w.add_subparsers(dest="web_cmd", required=True)
    for name, hp in (("create-admin", "관리자 계정 만들기(있으면 권한만 부여)"), ("reset-password", "비밀번호 재설정(기존 로그인 끊김)"),
                     ("revoke-admin", "관리자 권한 거두기"), ("export-dataset", "학습 데이터 내보내기(주간 작업 입력)"),
                     ("backup", "계정·기록 DB 백업(실행 중에도 가능)"), ("pilot-report", "파일럿 결과 지표·기법 비교 보고서"),
                     ("bootstrap", "첫 실행 준비: 번들 학습·운영 등록부·환경변수 관리자(이미 있으면 건너뜀)"), ("stats", "가입·기록 통계")):
        q = wsub.add_parser(name, help=hp)
        q.add_argument("--db", default=web_db, help=f"학습자 계정·기록 DB(기본 {web_db})")
        if name in ("create-admin", "reset-password", "revoke-admin"):
            q.add_argument("--username", required=True)
        if name == "export-dataset":
            q.add_argument("--out", required=True, help="profiles.csv·study_log.csv·catalog.csv를 쓸 폴더")
            q.add_argument("--bundle", default=None, help="카탈로그를 가져올 번들(기본: 기본 카탈로그 v2)")
            q.add_argument("--include-current-week", action="store_true", help="진행 중인 주의 기록도 넣는다(기본: 끝난 주까지만)")
        if name == "backup":
            q.add_argument("--out", required=True, help="사본 경로(예: runs/web/backup-20261102.db, 있으면 거절)")
        if name == "bootstrap":
            q.add_argument("--bundle", default="runs/seed42", help="번들 폴더(없으면 학습)")
            q.add_argument("--ops-dir", default="runs/ops", help="운영 등록부 폴더(없으면 생성, 빈 문자열이면 건너뜀)")
            q.add_argument("--n", type=int, default=None,
                           help="번들을 새로 학습할 때 모의 학습자 수(기본: 컨테이너 메모리에 맞춰 15,000 또는 3,000, 환경변수 ETFREC_BOOTSTRAP_N)")
        if name == "pilot-report":
            q.add_argument("--out", default="results/pilot", help="보고서 폴더(기본 results/pilot)")
            q.add_argument("--bundle", default=None, help="기법 비교에 쓸 번들(기본: --ops-dir 등록부의 서빙 번들)")
            q.add_argument("--ops-dir", default="runs/ops")
            q.add_argument("--window-days", type=int, default=7, help="통과를 세는 관측 창(일, 기본 7)")
            q.add_argument("--k", type=int, default=5)
            q.add_argument("--no-compare", action="store_true", help="기법 비교를 건너뛴다(번들 없이 빠르게)")
            q.add_argument("--as-of", default=None, help="분석 기준일 YYYY-MM-DD(그날까지의 기록만, 기본: 지금)")
    w.set_defaults(fn=cmd_web)
    dk = sub.add_parser("desktop", help="내 컴퓨터를 파일럿 서버로: 서버+터널, 자동 재시작, 절전 방지, 매일 백업")
    dk.add_argument("--port", type=int, default=8000)
    dk.add_argument("--tunnel", choices=("auto", "token", "quick", "none"), default="auto",
                    help="auto: 토큰이 있으면 고정 주소, 없으면 임시 주소, cloudflared가 없으면 같은 와이파이(none)")
    dk.add_argument("--db", default=web_db)
    dk.add_argument("--ops-dir", default="runs/ops", help="운영 루프 폴더(빈 문자열이면 끔)")
    dk.add_argument("--bundle", default="runs/seed42", help="번들 폴더(없으면 첫 실행 때 학습)")
    dk.add_argument("--designs", default="runs/designs")
    dk.add_argument("--backup-dir", default="runs/web/backups", help="백업 폴더(OneDrive·iCloud 같은 동기화 폴더를 주면 다른 곳에도 남는다)")
    dk.add_argument("--backup-hour", type=int, default=4, help="매일 백업할 시각(0~23시, 기본 4시)")
    dk.add_argument("--keep-backups", type=int, default=14, help="남길 백업 개수(기본 14)")
    dk.add_argument("--desktop-dir", default=None, help="로그·주소·터널 토큰 폴더(기본 runs/desktop)")
    dk.add_argument("--n", type=int, default=None, help="번들을 새로 학습할 때 모의 학습자 수(기본: 메모리에 맞춰 자동)")
    dk.add_argument("--no-prompt", action="store_true", help="관리자 계정을 묻지 않는다(자동 시작용)")
    dk.set_defaults(fn=cmd_desktop)
    a = p.parse_args(argv)
    get_logger()
    a.fn(a)


if __name__ == "__main__":
    main()
