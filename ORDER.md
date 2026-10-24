# Product order and contract POC

The CPQ journey now ends with a **TMF622-style ProductOrder request** and a proposed service-order payload. It runs locally and on private Cloud Run. It is a POC implementation of the current catalogue, not a TM Forum conformance-certified server or a live network order.

## Journey

1. Select an Active Product Offering in CPQ and validate the quote. The server retains the exact customer, catalogue, rule and CPQ policy snapshots used for the quote.
2. For a `VALIDATED` quote, the UI prepares a `ProductOrder` request body and POSTs it to `/tmf-api/productOrderingManagement/v5/productOrder`. Pending approvals and stale quotes cannot be submitted. A duplicate request for the same quote returns the original order.
   New mobile order references use `MOB-HHMM-DDMMYYYY-NNNN`, with the time and date in UTC. For example, the first order at 22:26 UTC on 24 October 2026 is `MOB-2226-24102026-0001`; the next in that minute is `...-0002`. The sequence resets when the UTC minute changes and is determined from persisted orders. Previously issued `order-...` references remain valid.
3. The response is an acknowledged **POC order record**. The service-order view resolves each ordered composite Product Specification into leaf specifications and their mapped CFS actions. For Mobile Mini, these are voice/HSS, data/packet-gateway customer profile and messaging/SMSC. Extra SMS adds a further messaging CFS action. The payload does not select RFS or activate a network.
4. The order page exposes both JSON payloads, a downloadable draft contract PDF and an optional **Email draft PDF** action with a primary and optional copy address.

The [TMF622 v5 API overview](https://www.tmforum.org/open-digital-architecture/open-apis/product-ordering-management-api-TMF622/v5.0) and [v5 OpenAPI definition](https://github.com/tmforum-apis/TMF622_ProductOrder/blob/main/TMF622-ProductOrdering-v5.0.0.oas.yaml) informed the route and `ProductOrder` fields. The service-order payload follows the [TMF641 CFS service-order pattern](https://www.tmforum.org/oda/directory/components-map/core-commerce-management/TMFC007). The JSON examples are [ProductOrder](review/tmf622-product-order-example.json) and [CFS service order](review/cfs-service-order-example.json).

## Contract verification

The [sample PDF](review/draft-contract-summary.pdf) is clearly marked **draft and non-binding**. It includes Jason Smith, the ordered offers, allowances, term, quoted monthly price before tax and estimated selected-term charges. The product order is a technical POC record, not evidence that the customer accepted a binding agreement.

UK telecom customers need written contract summary and detailed information before consent, including price, contract length and cancellation information; the customer must give express consent after receiving the summary. See [Ofcom's contract guidance](https://www.ofcom.org.uk/make-a-complaint/complain-about-mobile-phone-or-internet-services/contracts?language=en) and its [contract-summary enforcement explanation](https://www.ofcom.org.uk/siteassets/resources/documents/about-ofcom/bulletins/enforcement-bulletin/all-cases/cw_01265/non-confidential-confirmation-decision---bt-contract-information-and-contract-summary-investigation.pdf?v=388129). New UK consumer contracts with planned mid-contract increases must state the amounts and dates in pounds and pence, rather than linking them to inflation or a percentage; see [Ofcom's price-rise guidance](https://www.ofcom.org.uk/phones-and-broadband/saving-money/telecoms-price-rises-what-are-your-rights). The POC models no increase and makes no provider promise about future prices.

The contract review flags missing provider identity, tax-inclusive pricing, extra usage charges, cancellation and early termination terms, complaints details, and service activation/quality terms. These must be specified and reviewed before turning the PDF into a binding UK contract. A distance sale may also have statutory cancellation requirements; see the [Consumer Contracts Regulations](https://www.legislation.gov.uk/uksi/2013/3134/part/3/made).

## Optional email

Email is sent only after a person presses **Email draft PDF with Google**, authorizes the configured Gmail sender, and supplies a real recipient. The example.com address cannot be used for delivery. Cloud Run uses the Gmail API with a short-lived `gmail.send` token; it does not store a mailbox password or refresh token. Local SMTP remains an optional alternative when configured with `SMTP_HOST`, `SMTP_FROM`, `SMTP_PORT` (default `587`), and optionally `SMTP_USERNAME` and `SMTP_PASSWORD`. The PDF remains downloadable without email. Automated tests use fake delivery clients; a real Gmail send requires mailbox consent in the browser.

## Reproduce

```powershell
.venv\Scripts\python.exe review\build_order_example.py
.venv\Scripts\python.exe -m pytest -q
```
