import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from etfrec.config import TrainConfig  # noqa: E402
from etfrec.data import Dataset  # noqa: E402
from etfrec.pipeline import train  # noqa: E402
from etfrec.neural import HAS_TORCH  # noqa: E402


@pytest.fixture(scope="session")
def small_bundle():
    """작은 모의 세계(학습자 600명)로 전체 파이프라인을 한 번 돌린 번들. torch가 없으면 MF·MLP 없이 학습한다."""
    cfg = TrainConfig(n_learners=600, seed=42, router_reps=1, bootstrap_n=50)
    ds = Dataset.synthetic(cfg)
    return train(ds, cfg, out_dir=None, enable_neural=HAS_TORCH, log=lambda *a, **k: None)
