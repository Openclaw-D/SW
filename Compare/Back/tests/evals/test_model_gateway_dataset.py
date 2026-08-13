from __future__ import annotations

import json
from dataclasses import fields

import pytest

from evals.model_gateway.dataset import (
    HIDDEN_TRUTH_PATH,
    PUBLIC_DATASET_PATH,
    assert_dataset_alignment,
    load_hidden_truth,
    load_public_cases,
)
from evals.model_gateway.live_policy import load_live_eval_policy


def test_public_and_hidden_datasets_have_24_aligned_cases_and_six_industry_smoke() -> None:
    public_cases = load_public_cases()
    truths = load_hidden_truth()
    assert_dataset_alignment(public_cases, truths)

    smoke_cases = [case for case in public_cases if case.smoke]
    assert len(public_cases) == 24
    assert len(smoke_cases) == 6
    assert len({case.industry for case in smoke_cases}) == 6


def test_hidden_truth_is_physically_separate_and_absent_from_provider_input() -> None:
    assert PUBLIC_DATASET_PATH.parent != HIDDEN_TRUTH_PATH.parent
    public_text = PUBLIC_DATASET_PATH.read_text(encoding="utf-8")
    assert "expectedFields" not in public_text
    assert "goldenTruth" not in public_text
    assert "hiddenTruth" not in public_text
    for case in load_public_cases():
        serialized = json.dumps(dict(case.provider_input), ensure_ascii=False)
        assert "expectedFields" not in serialized
        assert "goldenTruth" not in serialized
        assert "hiddenTruth" not in serialized
        assert case.provider_input["isSimulated"] is True
        assert case.provider_input["dataStatus"] == "synthetic_demo"
        assert case.provider_input["source"]
        assert case.provider_input["disclaimer"]


def test_public_case_type_cannot_serialize_hidden_truth() -> None:
    case = load_public_cases()[0]
    assert {item.name for item in fields(case)} == {
        "case_id",
        "industry",
        "smoke",
        "provider_input",
    }


def test_real_provider_policy_is_hard_off_by_default() -> None:
    policy = load_live_eval_policy()
    assert policy.enabled is False
    assert policy.max_calls == 0
    assert policy.budget_ceiling_units == 0
    with pytest.raises(PermissionError, match="disabled"):
        policy.assert_allowed()
