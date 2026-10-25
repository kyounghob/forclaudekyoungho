"""Declared operational rule; deliberately outside the validation search zoo.

The positive goal and roadmap weights are requirements of the proposed service,
not components that may disappear when a validation winner changes.
"""
from __future__ import annotations

from .zoo import Algo

POLICY_KEY = "PurposeStageRule"
POLICY_LABEL = "목적 단계 규칙"
POLICY_VERSION = "2026-10-23-purpose-stage-v1"
POLICY_WEIGHTS = (("pop", 5.0), ("r:policy_pref", 3.0), ("r:lvl", 2.0),
                  ("r:dev", 1.0), ("r:goal", 2.0), ("r:roadmap", 2.0))


def purpose_stage_algorithm() -> Algo:
    """Stable policy key is primary; -1 means no historical zoo configuration id."""
    return Algo(-1, "PURPOSE_STAGE", POLICY_LABEL,
                [(name, ("c", weight)) for name, weight in POLICY_WEIGHTS], (),
                "3-2(프로젝트 고정 설계)",
                dict(policy_key=POLICY_KEY, policy_version=POLICY_VERSION,
                     declared_policy=True, selected_by_validation=False))


def policy_metadata() -> dict:
    return dict(key=POLICY_KEY, name=POLICY_LABEL, version=POLICY_VERSION,
                weights=dict(POLICY_WEIGHTS), declared_policy=True,
                historical_zoo_id=None, selected_by_validation=False,
                design_context="declared in this revision after prior synthetic results were available; not retrospective preregistration",
                normalization=dict(pop="candidate-row min-max; constant row -> 0",
                                   rules="raw: binary pref/level/device; goal affinity in [0,1]; roadmap 1/.7/.4/0",
                                   preference="declared interests plus historical top-two topics only when actual behaviour Rw has nonzero entries; diagnostic admission is not behaviour"),
                protected_inputs_used=[], inputs=["global historical pass popularity", "interests", "learning preferences",
                                                  "level", "device", "goal", "risk", "horizon", "passed units"],
                goal_affinity_limitation="Goal affinity is declared domain knowledge also used by the synthetic generator; synthetic superiority is not independent evidence.",
                replacement_rule=dict(applies_to="future policy changes from this revision; not retroactive pre-registration",
                                      min_ndcg_gain=0.005, goal_and_roadmap_terms_required=True,
                                      purpose_stage_noninferiority=True, prerequisite_violation_rate=0.0,
                                      confirmation="new data after policy freeze; synthetic checks do not establish learner effect"))
