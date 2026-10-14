"""명령줄 인터페이스.

    python -m etfrec generate --out data/synthetic [--n 15000] [--seed 42] [--effect 1.0]
    python -m etfrec train --out artifacts/bundle_v1 [--data data/synthetic] [--n 15000] [--no-neural]
    python -m etfrec recommend --bundle artifacts/bundle_v1 --user 1 [--k 5] [--algorithm RULE]
    python -m etfrec serve --bundle artifacts/bundle_v1 [--host 127.0.0.1] [--port 8000]
    python -m etfrec demo [--n 3000]      # 작은 규모로 학습한 뒤 바로 서버를 띄운다
    ETFREC_PSEUDO_KEY=... python -m etfrec pseudonymize --profiles A.csv --log B.csv --id-col member_id --out DIR --mapping-out PATH
    python -m etfrec export-deid --bundle artifacts/bundle_v2 --k 5 --out FILE.csv [--report FILE.json]
    python -m etfrec sources list|check|sync|stats [--out data/sources] [--krx-csv 내려받은.csv|.xlsx] [--krx-csv-date YYYYMMDD] [--date YYYYMMDD] [--krx-key KEY] [--datagokr-key KEY] [--no-cross-check]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .config import TrainConfig
from .data import Dataset
from .util import get_logger, json_safe


def cmd_sources(a):
    from .sources import SOURCES, load_etf_universe, sync_all, type_stats
    from .sources.sync import check_sources
    if a.action == "list":
        for k, v in SOURCES.items():
            print(f"- {k}: {v['name']} | {v['url'] or '-'} | {v['menu']} | 접근: {v['access']} | 확인: {v['verified']}")
    elif a.action == "check":                                  # 출처 루트마다 HEAD 1회
        for r in check_sources():
            print(f"{r['status']:40s} {r['name']}  {r['url']}")
    elif a.action == "sync":
        prov = sync_all(a.out, datagokr_key=a.datagokr_key, bas_dt=a.date, krx_csv=a.krx_csv, krx_key=a.krx_key,
                        krx_csv_date=a.krx_csv_date, cross_check=not a.no_cross_check)
        print(json.dumps(prov, ensure_ascii=False, indent=2))
    elif a.action == "stats":
        df, prov = load_etf_universe(a.out)
        print(prov["label"], "| rows", len(df))
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
    cfg = TrainConfig(n_learners=a.n, seed=a.seed, effect_scale=a.effect, catalog_version=a.catalog_version, generator_version=a.generator_version)
    ds = Dataset.from_csv(a.data) if a.data else Dataset.synthetic(cfg)
    bundle = train(ds, cfg, out_dir=a.out, enable_neural=not a.no_neural)
    print("운영 설정:", bundle.algos[bundle.selection["operational_algorithm"]].name)


def cmd_recommend(a):
    from .pipeline import Bundle
    from .service import RecommendationService
    svc = RecommendationService(Bundle.load(a.bundle))
    algorithm = int(a.algorithm) if a.algorithm and a.algorithm.isdigit() else a.algorithm
    out = svc.recommend(a.user, k=a.k, algorithm=algorithm)
    print(json.dumps(json_safe({k: v for k, v in out.items() if k != "topic_map"}), ensure_ascii=False, indent=2))


def cmd_serve(a):
    import uvicorn
    from .api import create_app
    app = create_app(a.bundle, designs_dir=a.designs)
    print(f"http://{a.host}:{a.port}  (번들 {a.bundle})")
    uvicorn.run(app, host=a.host, port=a.port, log_level="info")


def cmd_demo(a):
    from .pipeline import train
    out = a.out
    if not os.path.exists(os.path.join(out, "bundle.pkl")):
        cfg = TrainConfig(n_learners=a.n)
        train(Dataset.synthetic(cfg), cfg, out_dir=out, enable_neural=not a.no_neural)
    a.bundle = out; a.designs = None
    cmd_serve(a)


def cmd_pseudonymize(a):
    """운영 원본 → 가명 학습 입력(profiles.csv·study_log.csv). 키는 환경변수에서만 읽고, 매핑표는 --mapping-out에만 쓴다."""
    import pandas as pd
    from .privacy import KEY_ENV, MIN_KEY_LENGTH, build_pseudonymized_inputs
    key = os.environ.get(KEY_ENV, "")
    if len(key) < MIN_KEY_LENGTH:
        sys.exit(f"{KEY_ENV} 환경변수에 {MIN_KEY_LENGTH}자 이상의 가명처리 키가 없어 실행하지 않습니다(키는 명령줄 인자로 받지 않음)")
    out, mp = os.path.abspath(a.out), os.path.abspath(a.mapping_out)
    if os.path.commonpath([out, mp]) == out:
        sys.exit("매핑표(--mapping-out)는 학습 입력 폴더(--out) 밖, 학습 환경과 분리된 곳에 두어야 합니다")
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
    print(json.dumps(dict(users=len(profiles), log_rows=len(log), training_input=out, mapping=mp,
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


def main(argv=None):
    p = argparse.ArgumentParser(prog="etfrec", description="ETF 교육 콘텐츠 개인화·세그먼트 추천 시스템")
    sub = p.add_subparsers(dest="cmd", required=True)
    def versions(parser):
        parser.add_argument("--catalog-version", type=int, default=TrainConfig().catalog_version, help="1 = 노트북 원본 60단원, 2 = 63단원+선수 관계")
        parser.add_argument("--generator-version", type=int, default=TrainConfig().generator_version, help="1 = 노트북 난수 순서, 2 = 목적·선수 관계 반영")
    g = sub.add_parser("generate", help="모의 데이터 생성 → CSV"); g.add_argument("--out", required=True)
    g.add_argument("--n", type=int, default=TrainConfig().n_learners); g.add_argument("--seed", type=int, default=TrainConfig().seed)
    g.add_argument("--effect", type=float, default=TrainConfig().effect_scale); versions(g); g.set_defaults(fn=cmd_generate)
    t = sub.add_parser("train", help="학습 → 검증 → 선택 → 테스트 → 번들 저장"); t.add_argument("--out", required=True)
    t.add_argument("--data", default=None, help="profiles.csv·study_log.csv·catalog.csv가 있는 폴더(없으면 모의 데이터)")
    t.add_argument("--n", type=int, default=TrainConfig().n_learners); t.add_argument("--seed", type=int, default=TrainConfig().seed)
    t.add_argument("--effect", type=float, default=TrainConfig().effect_scale); t.add_argument("--no-neural", action="store_true")
    versions(t); t.set_defaults(fn=cmd_train)
    so = sub.add_parser("sources", help="공개 데이터 출처 목록·접근 점검·스냅샷 동기화·유형 통계")
    so.add_argument("action", choices=["list", "check", "sync", "stats"]); so.add_argument("--out", default=os.path.join("data", "sources"))
    so.add_argument("--datagokr-key", default=None, help="공공데이터포털 serviceKey (환경변수 DATA_GO_KR_KEY도 가능)")
    so.add_argument("--date", default=None, help="API 기준일 YYYYMMDD(기본: 직전 평일. 휴장일·미공개면 응답 0행 → empty로 기록)")
    so.add_argument("--krx-csv", default=None, help="KRX 정보데이터시스템에서 직접 내려받은 'ETF 전종목 기본정보' 파일(CSV, 또는 openpyxl·xlrd 설치 시 Excel). 화면 자동 호출은 하지 않음")
    so.add_argument("--krx-csv-date", default=None, help="내려받은 파일의 기준일 YYYYMMDD(없으면 파일 수정일을 '내려받은 날'로 기록)")
    so.add_argument("--no-cross-check", action="store_true", help="공공데이터포털 KRX상장종목정보로 단축코드·ISIN을 교차 확인하지 않음")
    so.add_argument("--krx-key", default=None, help="KRX Open API 인증키(환경변수 KRX_OPEN_API_KEY도 가능)"); so.set_defaults(fn=cmd_sources)
    r = sub.add_parser("recommend", help="번들로 한 학습자 추천"); r.add_argument("--bundle", required=True)
    r.add_argument("--user", type=int, required=True); r.add_argument("--k", type=int, default=5); r.add_argument("--algorithm", default=None)
    r.set_defaults(fn=cmd_recommend)
    s = sub.add_parser("serve", help="API + UI 서버"); s.add_argument("--bundle", required=True)
    s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8000); s.add_argument("--designs", default=None)
    s.set_defaults(fn=cmd_serve)
    d = sub.add_parser("demo", help="작은 규모 학습 후 바로 서버 실행"); d.add_argument("--n", type=int, default=3000)
    d.add_argument("--out", default="artifacts/demo_bundle"); d.add_argument("--host", default="127.0.0.1"); d.add_argument("--port", type=int, default=8000)
    d.add_argument("--no-neural", action="store_true"); d.set_defaults(fn=cmd_demo)
    ps = sub.add_parser("pseudonymize", help="운영 원본(외부 회원 ID) → 가명 학습 입력 + 별도 매핑표 (키: 환경변수 ETFREC_PSEUDO_KEY)")
    ps.add_argument("--profiles", required=True, help="외부 ID 열이 있는 프로필 CSV"); ps.add_argument("--log", required=True, help="외부 ID 열이 있는 학습 로그 CSV")
    ps.add_argument("--id-col", required=True, help="외부 회원 ID 열 이름"); ps.add_argument("--out", required=True, help="학습 입력 폴더(profiles.csv·study_log.csv)")
    ps.add_argument("--mapping-out", required=True, help="매핑표 CSV 경로(학습 환경 밖, --out 안이면 거부)"); ps.set_defaults(fn=cmd_pseudonymize)
    ex = sub.add_parser("export-deid", help="번들 저장 프로필 → k-익명 학습자 표(일반화 → 국소 억제) + 보고서")
    ex.add_argument("--bundle", required=True); ex.add_argument("--k", type=int, default=5); ex.add_argument("--out", required=True)
    ex.add_argument("--report", default=None, help="보고서 JSON 경로(기본: --out 이름 + _report.json)"); ex.set_defaults(fn=cmd_export_deid)
    a = p.parse_args(argv)
    get_logger()
    a.fn(a)


if __name__ == "__main__":
    main()
