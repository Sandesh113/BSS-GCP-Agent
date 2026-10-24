"""Offline regression for the agent boundary and current catalogue/CPQ journey.

The proposals are labelled fixtures, not live model responses. Use run.py for
model accuracy once an Agent Runtime resource is deployed.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalogue_core import ValidationError, build_result
from cpq_core import configure_quote
from customer_core import load_customers


CASES_PATH = Path(__file__).with_name("local_cases.json")


def grade(case, customer):
    try:
        if case["kind"] == "agent":
            result = build_result(case["request"], case["proposal"])
            cfs = [item["service"]["serviceSpecification"]["id"]
                   for item in (result["serviceOrder"] or {}).get("orderItem", [])]
            checks = {"status": result["status"] == case["expectedStatus"],
                      "monthly": result["quote"]["quoteTotalPrice"][0]["price"]["dutyFreeAmount"]["value"] == case["expectedMonthly"],
                      "cfs": cfs == case["expectedCfs"],
                      "approvalGate": (result["productOrder"] is None and result["serviceOrder"] is None)
                      if result["status"] == "PENDING_APPROVAL" else result["productOrder"] is not None}
        elif case["kind"] == "cpq":
            as_of = datetime.fromisoformat(case["asOf"]) if case.get("asOf") else None
            result = configure_quote(customer, case["selections"], case.get("promotionId"), as_of=as_of)
            checks = {"status": result["status"] == case["expectedStatus"],
                      "monthly": result["quote"]["quoteTotalPrice"][0]["price"]["dutyFreeAmount"]["value"] == case["expectedMonthly"],
                      "approvalGate": result["approval"]["required"] == (case["expectedStatus"] == "PENDING_APPROVAL")}
        else:
            raise ValueError(f"Unknown eval kind: {case['kind']}")
        if "expectedError" in case:
            checks = {"expectedRejection": False}
    except ValidationError as exc:
        checks = {"expectedRejection": case.get("expectedError", "") in str(exc) and "expectedError" in case}
    return {"caseId": case["id"], "kind": case["kind"], "passed": all(checks.values()), "checks": checks}


def run(cases=None):
    cases = cases if cases is not None else json.loads(CASES_PATH.read_text(encoding="utf-8"))
    customer = load_customers()["customers"][0]
    rows = [grade(case, customer) for case in cases]
    return {"mode": "offline-labelled-proposals", "passed": sum(row["passed"] for row in rows),
            "total": len(rows), "cases": rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="Optional JSON report path")
    args = parser.parse_args()
    report = run()
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] == report["total"] else 1)


if __name__ == "__main__":
    main()
