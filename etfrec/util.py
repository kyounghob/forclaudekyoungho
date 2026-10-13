"""작은 공용 도구."""
from __future__ import annotations

import logging
import sys

import numpy as np
import pandas as pd


def json_safe(o):
    """JSON으로 내보낼 때 numpy 값·NaN 정리(NaN → null)."""
    if isinstance(o, dict):
        return {str(k): json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [json_safe(v) for v in o]
    if isinstance(o, pd.DataFrame):
        return json_safe(o.to_dict("records"))
    if isinstance(o, pd.Series):
        return json_safe(o.tolist())
    if isinstance(o, np.ndarray):
        return json_safe(o.tolist())
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, (int, np.integer)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        f = float(o)
        return f if np.isfinite(f) else None
    return o


def get_logger(name: str = "etfrec") -> logging.Logger:
    log = logging.getLogger(name)
    if not log.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
    return log
