"""Ensure the offline evaluation detects drift instead of always passing."""

import copy
import json
from pathlib import Path

from eval.run_local import CASES_PATH, run


def test_labelled_journey_cases_pass_and_a_wrong_expectation_fails():
    cases = json.loads(Path(CASES_PATH).read_text(encoding="utf-8"))
    assert run(cases)["passed"] == len(cases)
    changed = copy.deepcopy(cases)
    changed[0]["expectedMonthly"] = "0.00"
    report = run(changed)
    assert report["passed"] == len(cases) - 1
    assert report["cases"][0]["checks"]["monthly"] is False
