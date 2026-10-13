"""명령줄 인터페이스.

    python -m etfrec generate --out data/synthetic [--n 15000] [--seed 42] [--effect 1.0]
    python -m etfrec train --out artifacts/bundle_v1 [--data data/synthetic] [--n 15000] [--no-neural]
    python -m etfrec recommend --bundle artifacts/bundle_v1 --user 1 [--k 5] [--algorithm RULE]
    python -m etfrec serve --bundle artifacts/bundle_v1 [--host 127.0.0.1] [--port 8000]
    python -m etfrec demo [--n 3000]      # 작은 규모로 학습한 뒤 바로 서버를 띄운다
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .config import TrainConfig
from .data import Dataset
from .util import get_logger, json_safe


def cmd_generate(a):
    cfg = TrainConfig(n_learners=a.n, seed=a.seed, effect_scale=a.effect)
    ds = Dataset.synthetic(cfg)
    ds.save_csv(a.out)
    print(json.dumps(ds.summary(), ensure_ascii=False, indent=2))
    print("저장:", os.path.abspath(a.out))


def cmd_train(a):
    from .pipeline import train
    cfg = TrainConfig(n_learners=a.n, seed=a.seed, effect_scale=a.effect)
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


def main(argv=None):
    p = argparse.ArgumentParser(prog="etfrec", description="ETF 교육 콘텐츠 개인화·세그먼트 추천 시스템")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="모의 데이터 생성 → CSV"); g.add_argument("--out", required=True)
    g.add_argument("--n", type=int, default=TrainConfig().n_learners); g.add_argument("--seed", type=int, default=TrainConfig().seed)
    g.add_argument("--effect", type=float, default=TrainConfig().effect_scale); g.set_defaults(fn=cmd_generate)
    t = sub.add_parser("train", help="학습 → 검증 → 선택 → 테스트 → 번들 저장"); t.add_argument("--out", required=True)
    t.add_argument("--data", default=None, help="profiles.csv·study_log.csv·catalog.csv가 있는 폴더(없으면 모의 데이터)")
    t.add_argument("--n", type=int, default=TrainConfig().n_learners); t.add_argument("--seed", type=int, default=TrainConfig().seed)
    t.add_argument("--effect", type=float, default=TrainConfig().effect_scale); t.add_argument("--no-neural", action="store_true")
    t.set_defaults(fn=cmd_train)
    r = sub.add_parser("recommend", help="번들로 한 학습자 추천"); r.add_argument("--bundle", required=True)
    r.add_argument("--user", type=int, required=True); r.add_argument("--k", type=int, default=5); r.add_argument("--algorithm", default=None)
    r.set_defaults(fn=cmd_recommend)
    s = sub.add_parser("serve", help="API + UI 서버"); s.add_argument("--bundle", required=True)
    s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8000); s.add_argument("--designs", default=None)
    s.set_defaults(fn=cmd_serve)
    d = sub.add_parser("demo", help="작은 규모 학습 후 바로 서버 실행"); d.add_argument("--n", type=int, default=3000)
    d.add_argument("--out", default="artifacts/demo_bundle"); d.add_argument("--host", default="127.0.0.1"); d.add_argument("--port", type=int, default=8000)
    d.add_argument("--no-neural", action="store_true"); d.set_defaults(fn=cmd_demo)
    a = p.parse_args(argv)
    get_logger()
    a.fn(a)


if __name__ == "__main__":
    main()
