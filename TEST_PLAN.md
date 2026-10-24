# Expert test plan and review — 24 October 2026

Scope: catalogue, decision tables, CPQ, TMF622 order, contract PDF, email, Pub/Sub function, agent, and guided assistant. The cases are in [tests/test_expert_review.py](tests/test_expert_review.py); IDs below match the test names. The updated UI, function, and agent were deployed to Google Cloud after the local review.

TM Forum references were checked against the published TMF648 v4.0.0 swagger (`QuoteStateType` = `rejected | pending | inProgress | cancelled | approved | accepted`; `Quote.validFor` is a `TimePeriod`; `Error` requires `code` and `reason`). The project remains **TMF-shaped**, not CTK-conformant.

## Result

| Run | Result |
| --- | --- |
| Original suite before changes | 70 passed. The run also rewrote the real `ui/quotes.json`. |
| New cases before fixes | 23 failed and 18 passed. Each failure reproduced one of the defects below. |
| Full suite after fixes | **111 passed**. The real `ui/quotes.json` was left unchanged. |
| `eval/run_local.py` | 17/17 labelled cases passed. |
| `catalogue_design/check_design.py` | Reference integrity OK. |
| Cloud journey after deployment | Passed: invalid TB-to-GB catalogue mapping rejected; quote validity period and approved state present; TMF622 order, three CFS actions and draft PDF created; Pub/Sub agent returned VALIDATED for the published offer, with no service-order or internal snapshots in the sales result. See [live journey report](eval/live_journey_report.json). |
| Terraform drift checks | UI and workload: no changes after deployment. |

## Faults found and fixed

| ID | Area | Fault | Fix |
| --- | --- | --- | --- |
| HYG-01 | Tests | Several tests did not redirect the quote/rule/catalogue stores, so `pytest` wrote into the real `ui/quotes.json` and could read a manager's saved `ui/draft.json`/`ui/rules.json` (non-hermetic). | `tests/conftest.py` isolates every store and clears cloud/mail env vars for every test. |
| CAT-01/02 | TMF620→TMF633 | Leaf PS unit was never compared with its CFS unit. A product manager could add a leaf with characteristic `dataGb` and unit `TB`; the save API copied the `cfs-data` (GB) mapping, so "1 TB" would be provisioned as 1 GB. | `validate_catalogue` requires each leaf unit to equal its mapped CFS unit. |
| CAT-03 | Catalogue API | A non-object row in `productOfferings`/`productSpecifications` raised `AttributeError` → HTTP 500. | Row shapes checked first → HTTP 400. |
| CPQ-01 | TMF648 | Quote `state` used `draft` and `pendingApproval`, which are not TMF648 values. | `approved` (priced, orderable) and `pending` (awaiting a human). |
| CPQ-02 / ORD-01 | TMF648 / TMF622 | Quotes had no validity period; a validated quote stayed orderable indefinitely while catalogue/rules were unchanged — even after a dated price row or promotion window ended. | Quotes carry `validFor` (30 days, `QUOTE_VALIDITY_DAYS`); order submission rejects expired quotes. Quotes saved before this change have no `validFor` and keep the old behaviour. |
| ORD-02 | TMF630 | `/tmf-api/...` errors returned `{"error": ...}` instead of the TMF Error resource. | `@type: Error`, `code`, `reason`, `message`, `status`; `error` kept for the existing UI scripts. |
| EML-01 | Email | Only exact `@example.com` was refused; `mail.example.com`, `example.org`, `example.net` (RFC 2606) passed. | All three reserved domains and their subdomains are refused. |
| EML-02 | Email | `a,b@customer.test` passed validation and became two `To:` recipients in the Gmail raw message. | Address pattern rejects list separators, brackets and quotes. |
| AGT-01 | Pub/Sub | A `RuleError` (for example, a bad saved rules file) escaped the handler. The trigger uses `RETRY_POLICY_RETRY` with no dead-letter topic, so the message would be retried indefinitely. | Deterministic `ValidationError`/`RuleError` → stored `REJECTED` result and status event. |
| AGT-02 | Pub/Sub cost | Every redelivery paid for another Gemini call before discovering the stored result. | Existing result is reused before the model is called. |
| AGT-03 | Agent input | The model received Draft/Retired offers and service design (HSS/SMSC targets, CFS IDs), against the product-manager/service-design boundary. The catalogue was also read twice per request (possible version skew). | Read once; model sees only Active offers and the specifications they reference, without CFS mappings. |
| AGT-04 | Agent output | Fenced (```` ```json ````) or non-JSON model output raised inside the Agent Runtime → HTTP 500 → retried. | `parse_proposal` strips fences and never raises; a non-object becomes an empty selection that the validator rejects. |
| AGT-05 | API exposure | `/api/agent/results/<id>` returned catalogue, rules and policy snapshots and the CFS service order to the commercial UI. | Returns only the fields the UI renders. |
| AST-01/02 | Guided assistant | A model reply with `"name": null` failed the whole turn, and an allowance of `"2"` was rejected. | Nulls mean "not stated"; numeric strings are read as numbers (range checks unchanged). |

## Regression guards (passed before and after)

CAT-04 nested/self bundles; CAT-05 service design cannot be smuggled through the PM API; RUL-01 per-item half-up rounding (33.33% → £8.00 + £1.67 = £9.67); RUL-02 `exists false` and `notIn`; RUL-03 disproved higher-priority row falls through; RUL-04 approval helper needs a pending quote and records rejection; CPQ-03 commitment uses each item's own term (£158.00); CPQ-04 promotion attribution and unknown promotion; CPQ-05 TMF679 segment qualification; ORD-03 order totals and per-item `itemTerm`; ORD-04 unknown quote reference; ORD-05 PDF xref offsets and text escaping; CUS-01 postcode/mobile normalisation and UK-only fields.

## Not changed — recommended next steps

1. **Dead-letter topic** for the request subscription (Terraform `infra/workload`). The code fix stops deterministic retries; transient model outages still retry without a cap. This needs a reviewed `plan`/`apply`.
2. **CFS instance merging (TMF641).** Mobile Mini + Extra SMS emits two `cfs-sms` actions. `MOBILE_PS_TO_CFS_RESEARCH.md` says shared CFSs should be merged per line. ORDER.md documents the current behaviour, so this is a design change.
3. **Active offerings are editable in place.** Price or allowance edits to an Active offer have no version bump (TMF620 `version`/`lastUpdate`). Prior orders keep their snapshots, but there is no audit of the change.
4. **Promotion quotes can never be ordered in the UI.** The seed approval table holds every discount, and there is no approval inbox.
5. **`ui/quotes.json` grows without bound.** Each quote stores full catalogue, rule and policy snapshots (about 18 KB each; 778 KB for 43 quotes). Store digests and deduplicate snapshots, or prune expired quotes.
6. **Cloud scope.** The UI, Pub/Sub function, and staged agent have been redeployed. The live journey covered the primary flow; fault injection and every negative case in this plan were verified locally, not individually against cloud services.
