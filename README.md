# BSS AI Agent on Google Cloud

The project models Product Offering → composite Product Specification → Voice/Data/SMS Product Specifications → Customer Facing Service (CFS) Specifications. The seeded **Mobile Mini** offer has 100 voice minutes, 2 GB of data and 100 SMS. The quote and acknowledged orders are TMF-shaped snapshots; they are not full TM Forum API implementations and do not provision network systems.

See [TMF_CATALOGUE_FEDERATION.md](TMF_CATALOGUE_FEDERATION.md) and [TMF_CFS_DECOMPOSITION.md](TMF_CFS_DECOMPOSITION.md) for TMF620/TMF633, SID, federation and example CFS research. The product manager UI shows leaf/composite product specifications and product offerings, with drag-and-drop composition. The underlying service design remains in the backend for order decomposition. The hosted request screen can submit to Gemini through Pub/Sub or preview a manually selected offer. Live catalogue federation remains a future integration.

The [modular rule reference library](catalogue_design/README.md) researched on 24 October 2026 defines 72 proposed rule templates across 12 families and binds the agreed ten PS/seven CFSS design. It includes contract/price schedules, compatibility, shared allowances, realization and lifecycle rules. These draft design files are not loaded by the current runtime; `catalogue_design/check_design.py` verifies their references and price examples.

The local preview also has an executable [business rules editor](BUSINESS_RULES.md): four configurable decision tables for **eligibility, prices, discounts and approvals**. Rows, conditions, effective dates and customer input columns can change without Python edits or a server restart. These four tables are the first runtime slice; they do not implement every template in the 72-rule library.

The [guided catalogue assistant](GUIDED_CATALOGUE.md) lets a product manager describe a product in natural language or answer questions about its specifications, price and customer segment. The hosted UI accepts typed answers and offers optional browser speech input. Gemini extracts suggestions; code validates them before saving a Draft. The [CPQ configurator](CPQ.md) starts with one fictional UK customer, Jason Smith, and presents Active offers as selectable plan tiles. Product managers use **Publish offer** to validate and activate a Draft; CPQ reads the saved catalogue when opened, so the offer becomes available immediately. **Retire offer** removes it from new selections while preserving existing order records. CPQ accepts multiple products, a contract term per item and an eligible dated promotion, then checks product relationships and calculates a TMF-shaped quote. Mobile Mini plus Extra SMS is the compatible example; Mobile Mini plus Mobile Plus is an illustrative incompatible pair. The UI and its saved records run on Google Cloud.

After a validated quote, the [product-order POC](ORDER.md) prepares and submits a TMF622-style ProductOrder JSON payload, decomposes the ordered Product Specifications into CFS service actions, and generates a draft contract PDF. Optional email delivery uses the configured Gmail sender after Google authorization and requires a real recipient. The cloud order flow performs no network activation or binding contract acceptance.

## Open the cloud UI

The Cloud Run service is private. Use the authenticated CLI proxy and open [http://127.0.0.1:8092](http://127.0.0.1:8092) while it is running. See [DEPLOYMENT.md](DEPLOYMENT.md) for the command, architecture, resource names and verification reports. A direct Google sign-in URL requires one-time IAP OAuth setup for this standalone trial project; public access is not enabled.

## Run the local UI

From the project root, run `.venv\\Scripts\\python.exe ui/app.py` and open [http://127.0.0.1:8088](http://127.0.0.1:8088). This local mode does not require a login and is bound to localhost. Local changes save to `ui/draft.json`; cloud changes save to the private state bucket. In **Catalogue Studio**, drag leaf product specifications into a composite specification. Set the allowance values, create an offering that references that composite, and save. A new specification without a known service mapping stays a draft; it cannot be sold until the technical team maps its realization. The manual request preview works locally; **Ask Gemini** requires the cloud deployment.

In **Business rules**, edit the four tables and their input columns, then choose **Save rules**. Local rules live in `ui/rules.json`; cloud rules live in the private state bucket. The next quote uses that version and displays its matching rules. All discounts and exceptions require human review under the seed policy. The hosted app is restricted to the project's operator through Cloud Run IAM; role-specific publication workflows are not implemented.

In **CPQ configurator**, Jason Smith is already in context. Select one or more product tiles, set each term, choose an active promotion if desired and validate the quote. The product tiles show allowance and term price before selection. The configurable term, compatibility and promotion rows are in `cpq_policy.json`.

## Current flow

`Pub/Sub request → Cloud Run function → LangChain agent on Vertex AI Agent Runtime → code validation/pricing → Cloud Storage result → Pub/Sub status`

The model selects published offering IDs. `catalogue_core.py` owns PO/PS/CFS relationship validation, allowance values and quote/order construction; `business_rules.py` evaluates configurable eligibility, price, discount and approval tables. Agent orders and CPQ share the product-combination rules. The seed policy requires a human decision for discounts and exceptions. Gemini 3.5 Flash on Vertex AI is the initial model, called through the EU multi-region endpoint; model provider, name and endpoint are Terraform inputs. The same cases in `eval/cases.json` can compare later providers. See [EVAL.md](EVAL.md) for local and live results.

## Infrastructure status

Google Cloud project `bss-ai-agent-20261021-sandesh` is linked to the user's confirmed Free Trial billing account. Terraform foundation (APIs and a £10 monthly gross-usage **alert**, not a spending cap), platform (private buckets, topics, audit subscription, service accounts and IAM), private Cloud Run UI with a state bucket, Vertex AI Agent Runtime and Pub/Sub-triggered Cloud Run function were planned and applied. The image is in private Artifact Registry. The hosted UI, cloud CPQ/order flow, status event and Gemini agent passed live checks on 24 October 2026. The $300 trial credit and account state should be monitored in the Google Cloud console.

## Local verification

From the project root, run `.venv\\Scripts\\python.exe -m pytest -q`. The seed request is:

```json
{"requestId":"demo-001","customerId":"customer-123","segment":"consumer","text":"I want a mobile plan with 100 minutes, 2GB data and 100 SMS."}
```

The CFS output lists proposed HSS, packet gateway/customer profile and SMSC actions. Network implementation adapters and a production catalogue source are future integration points.
