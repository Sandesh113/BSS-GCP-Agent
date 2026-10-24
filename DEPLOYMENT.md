# Google Cloud deployment

Project: `bss-ai-agent-20261021-sandesh`  
Application region: `europe-west2` (London)  
Model endpoint: `eu` multi-region (`gemini-3.5-flash`)

## Deployed path

```text
Authenticated browser proxy -> private Cloud Run catalogue/CPQ UI
                                   |-> private Cloud Storage state (catalogue, rules, quotes, orders)
                                   |-> TMF622-style order, PS-to-CFS actions, draft contract PDF
                                   `-> Pub/Sub customer request
                                         -> Cloud Run function
                                         -> Vertex AI Agent Runtime / Gemini
                                         -> code validation and pricing
                                         -> Cloud Storage result + Pub/Sub status
```

Terraform is split into `infra/foundation`, `infra/platform`, `infra/ui`, and `infra/workload`. Foundation enabled APIs and a £10 monthly **alert** before compute. An alert does not stop usage or impose a spending cap. All four modules have been applied. Images are stored in the private Artifact Registry repositories `bss-ui` and `bss-functions`. The status audit subscription retains messages for one day. The app has one Cloud Run instance at most and zero minimum instances.

## Open the hosted UI

The service is private and grants Cloud Run Invoker to the signed-in operator. Start the authenticated Google Cloud CLI proxy in a PowerShell terminal:

```powershell
& "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" run services proxy bss-catalogue-cpq --region europe-west2 --project bss-ai-agent-20261021-sandesh --port 8092
```

Then open [http://127.0.0.1:8092/](http://127.0.0.1:8092/). Keep that terminal running while using the UI. The stable Cloud Run URL is `https://bss-catalogue-cpq-yzfkynnqbq-nw.a.run.app`; a normal browser request to it does not carry the IAM token. Direct Google sign-in needs first-time IAP OAuth configuration for this standalone trial project. The service has not been made public.

To reopen a submitted POC order for contract download or email, append `?order=<order-id>` to the local proxy URL. The existing order `order-059986ddb78d` is available at `http://127.0.0.1:8092/?order=order-059986ddb78d`.

The **Catalogue Studio** has a **Create with Gemini** button for typed or optional recorded answers. The microphone records a short clip, the private Cloud Run service asks Gemini to transcribe it, and the manager reviews the text before submitting it. It saves a Draft offer to the private state bucket. **Publish offer** validates and activates one, after which it appears when the **CPQ configurator** opens. **Retire offer** stops new sales. CPQ creates quotes and orders for the fictional customer Jason Smith. **Customer request** has a manual preview and an **Ask Gemini** action that runs the Pub/Sub agent path. The contract PDF is downloadable after an acknowledged order. See [GUIDED_CATALOGUE.md](GUIDED_CATALOGUE.md) for the guided flow.

## Verification performed on 24 October 2026

- Expert-review release: rebuilt and deployed the private UI image, Pub/Sub function source, and Vertex agent package. The local suite passed 111 tests and the offline evaluation passed 17/17. One live cloud journey rejected a mismatched TB/GB specification, created an approved quote with `validFor`, submitted a mobile ProductOrder with three CFS actions, downloaded the draft PDF, and received a VALIDATED agent result containing only commercial fields (`eval/live_journey_report.json`). UI and workload Terraform plans both reported no drift afterward. The remaining design items and negative-case coverage are in `TEST_PLAN.md`.
- Mobile order reference release: Cloud Run revision `bss-catalogue-cpq-00008-hvg` serves image `poc-20261024-order-id-1`. New orders use `MOB-HHMM-DDMMYYYY-NNNN` in UTC; existing order references remain readable. The full local suite passed (70 tests), including same-minute sequence, idempotent replay, CFS linkage and PDF reference. The hosted CPQ options endpoint returned HTTP 200 and Terraform reported no drift. A fresh cloud order was not submitted solely for this release.
- Contract email update: Gmail API enabled, OAuth web client registered for `http://127.0.0.1:8092`, `gmail.send` scope and the project account configured as a test user. Cloud Run reports Gmail configured; the saved order reopens in CPQ. The local suite has 68 passing tests, including PDF attachment, duplicate recipient handling and sender enforcement. A real Gmail send remains to be confirmed after the mailbox owner grants consent in the browser.
- Local regression suite: 67 passed, including the new audio endpoint validation, guided Draft creation, draft publication, CPQ visibility, order creation, retirement and failed publication.
- Live voice transcription: a synthetic UK English WAV recording sent through the deployed private Cloud Run endpoint returned the expected editable text. A real browser microphone remains subject to the user's device and permission settings.
- Live guided authoring: Gemini extracted an offer name, two allowances, price and segment from one natural-language description. The new Draft was hidden from CPQ until Publish; it then produced a validated quote, acknowledged order and two CFS actions (`eval/live_assistant_report.json`).
- Live lifecycle test: a fresh Draft offer was hidden from CPQ and rejected by quote validation; after Publish it appeared in CPQ, returned a validated £15 monthly quote, produced an acknowledged order with three CFS actions and a draft PDF (`eval/live_lifecycle_report.json`).
- Live Vertex AI evaluation: six of six exact offer selections and six of six expected guardrail outcomes (`eval/live_report.json`).
- Live newly created offer: saved to the cloud catalogue, appeared in CPQ, produced a validated quote and acknowledged order, decomposed into three CFS actions, and returned a PDF. Gemini selected the newly created offer (`eval/live_journey_report.json`).
- A separate live request produced a `VALIDATED` Pub/Sub status event with a Cloud Storage result URI; it was pulled from the status audit subscription.
- A prior Mobile Mini plus Extra SMS cloud order produced four CFS actions and a readable draft contract PDF (`review/live-cloud-draft-contract.pdf`).

To repeat the application journey while the proxy is running:

```powershell
.venv\Scripts\python.exe eval\live_journey.py --base-url http://127.0.0.1:8092 --output eval\live_journey_report.json
.venv\Scripts\python.exe eval\live_lifecycle.py --base-url http://127.0.0.1:8092 --output eval\live_lifecycle_report.json
.venv\Scripts\python.exe eval\live_assistant.py --base-url http://127.0.0.1:8092 --output eval\live_assistant_report.json
```

The first script is idempotent for catalogue creation but creates a fresh quote and order on each run. The lifecycle script creates a fresh demonstration offer and order on each run. To inspect cloud changes before applying them, run `terraform --% plan -input=false -out=change.tfplan` from PowerShell in the affected module and apply that saved plan only after review. Build and push a new UI image tag before planning a changed Cloud Run image reference.

## POC boundaries

- Product orders are TMF622-shaped, not TM Forum CTK-certified. CFS actions are proposed payloads; no HSS, packet gateway, SMSC or other network activation occurs.
- The PDF is explicitly a draft summary. Provider legal details, VAT-inclusive charges, cancellation terms, consent and other final contract requirements remain unconfigured.
- Contract email uses the Gmail API after the operator clicks **Email draft PDF with Google** and authorizes the sending mailbox. The app requests a short-lived token with `gmail.send`, `openid`, and `email`; it does not store a mailbox password or refresh token. `GMAIL_SENDER_EMAIL` restricts the sending identity. The Google Auth Platform web client must include the local proxy origin `http://127.0.0.1:8092`, and the sender must be a test user while the OAuth app remains in Testing. Gmail acceptance returns a message ID; inbox delivery is checked separately. The draft is not a binding contract.
- Direct IAP sign-in, role-specific catalogue approval, automated deployment, and live catalogue federation are future work.
- Cloud Storage state is suitable for this single-instance POC. A multi-instance deployment needs transactional storage and a fuller authorisation model.
