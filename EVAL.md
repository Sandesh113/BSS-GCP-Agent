# Catalogue-to-quote evaluation

This suite covers the local implementation and the deployed Google Cloud POC. The 17 labelled offline cases in `eval/local_cases.json` pass fixed proposals through the same deterministic validator used after an agent response, then check quote status, monthly price, approval gating and CFS decomposition. They also cover CPQ term pricing, compatible and incompatible baskets, add-on requirements and dated promotions. The JSON report is `eval/local_report.json`.

Run from the project root:

```powershell
.venv\Scripts\python.exe eval\run_local.py --output eval\local_report.json
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe catalogue_design\check_design.py
```

The pytest suite additionally exercises the catalogue and CPQ HTTP endpoints: a saved composite Product Specification becomes a selectable Product Offering, can be quoted, and decomposes into the expected CFS actions. It probes invalid allowances, invented and duplicate offering IDs, model-supplied price changes, invalid terms, promotion boundaries and approvals. In-memory CloudEvent tests cover the function's result write, status event, rejected request and duplicate Pub/Sub delivery without contacting GCP.

The order tests cover TMF622-style payload construction from a stored validated quote, PS-to-CFS actions, idempotent submission, rejection of tampered or stale payloads, blocking pending approvals, PDF generation, fictional-address rejection and SMTP delivery with a fake client. These tests do not assert TM Forum CTK conformance or UK legal contract compliance.

The expert review of 24 October 2026 added 41 cases (`tests/test_expert_review.py`) and fixed 14 defects; see [TEST_PLAN.md](TEST_PLAN.md) for the case list, faults and remaining recommendations.

## Findings from this pass

1. A composite allowance of `NaN` or infinity passed catalogue validation. The validator now requires a finite positive number, and regression cases cover it.
2. CPQ enforced product compatibility, but the agent-to-order path did not. Extra SMS alone could produce an acknowledged order. Both paths now call the same product-constraint evaluator; the agent result stores the policy snapshot for later approval.
3. Sharing that validator added Cloud Run source dependencies absent from the Terraform archive. The workload archive now includes the shared validator, CPQ policy and its Python dependencies; a regression check guards the manifest.

## Live model evaluation

`eval/cases.json` contains six natural-language requests for comparing model providers. `eval/run.py` submits them to a deployed Agent Runtime resource and reports exact offering selection and whether the deterministic guardrail outcome matched the label. One case intentionally expects an orphan add-on proposal to be rejected. The live Gemini 3.5 Flash run on 24 October 2026 is in `eval/live_report.json`: all six cases had the exact labelled offering set and guardrail outcome. Five were valid; the orphan Extra SMS case was correctly rejected. The `eval/live_journey_report.json` cloud run created and published a new 3 GB demo offer, quoted and ordered it, verified three CFS actions and a PDF, then confirmed Gemini selected that new offer through the Pub/Sub path. A separate status subscription pull confirmed a matching `VALIDATED` event with a Cloud Storage result URI. These tests do not assert TM Forum CTK conformance, network activation, legal contract compliance or real email delivery.
