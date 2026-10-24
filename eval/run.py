"""Run the same labelled requests against any deployed Agent Runtime resource."""

import argparse
import json
import sys
from pathlib import Path

import google.auth
from google.auth.transport.requests import AuthorizedSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bss_core import CATALOGUE, ValidationError, build_result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-resource", required=True, help="projects/.../locations/.../reasoningEngines/...")
    parser.add_argument("--model-label", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    region = args.agent_resource.split("/locations/")[1].split("/")[0]
    url = f"https://{region}-aiplatform.googleapis.com/v1/{args.agent_resource}:query"
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)
    cases = json.loads((Path(__file__).parent / "cases.json").read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        response = session.post(url, json={
            "class_method": "query",
            "input": {"input": json.dumps({"request": case["request"], "catalogue": CATALOGUE})}
        }, timeout=180)
        if not response.ok:
            raise RuntimeError(f"Agent query failed ({response.status_code}): {response.text[:1200]}")
        payload = response.json()
        proposal = payload.get("output", payload) if isinstance(payload, dict) else payload
        if isinstance(proposal, str):
            try:
                proposal = json.loads(proposal)
            except json.JSONDecodeError:
                pass
        expected = set(case["expectedProductOfferingIds"])
        raw_ids = proposal.get("productOfferingIds", []) if isinstance(proposal, dict) else []
        predicted = set(item for item in raw_ids if isinstance(item, str)) if isinstance(raw_ids, list) else set()
        try:
            result = build_result(case["request"], proposal)
            valid = True
            status = result["status"]
        except ValidationError:
            valid = False
            status = "INVALID"
        rows.append({"caseId": case["request"]["requestId"], "expected": sorted(expected),
                     "predicted": sorted(predicted), "exactMatch": predicted == expected,
                     "valid": valid, "expectedValid": case.get("expectedValid", True),
                     "guardrailMatch": valid == case.get("expectedValid", True), "status": status})
    report = {"model": args.model_label, "agentResource": args.agent_resource,
              "exactMatchRate": sum(row["exactMatch"] for row in rows) / len(rows),
              "guardrailMatchRate": sum(row["guardrailMatch"] for row in rows) / len(rows),
              "validRate": sum(row["valid"] for row in rows) / len(rows), "cases": rows}
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("model", "exactMatchRate", "guardrailMatchRate", "validRate")}, indent=2))


if __name__ == "__main__":
    main()
