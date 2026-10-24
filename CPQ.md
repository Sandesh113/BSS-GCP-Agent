# CPQ configurator

The **CPQ configurator** screen turns one fictional UK customer and one or more catalogue offerings into a checked, priced quote. It runs locally and on private Cloud Run as a POC based on TM Forum concepts, not a certified implementation of the Open APIs. The offer presentation follows the public plan-card pattern seen on [Lebara's UK SIM-only page](https://www.lebara.co.uk/en/best-sim-only-deals.html) and [Vodafone's UK SIM-only page](https://www.vodafone.co.uk/sim-only/best-sim-only-deals): visible allowance, monthly price, term and a selection action. The plans and prices shown in our UI come from our own illustrative catalogue.

## Try the example

1. Open the UI and choose **CPQ configurator**. The journey begins with Jason Smith, one fictional UK customer, already in context. There is no customer picker in this CPQ step.
2. Select the **Mobile Mini** tile, choose 9, 12 or 16 months on that tile, then select **Extra SMS**. The seeded 12-month basket is £14.50 per month before tax and passes the compatibility checks.
3. Replace Extra SMS with **Mobile Plus**. The example policy rejects that combination because it treats Mini and Plus as alternative primary plans in one quote. This is our sample commercial rule, not a universal telecom rule about a customer's ability to hold multiple mobile lines.
4. Restore Extra SMS and select **Welcome offer**. Only eligible items receive its 5% reduction. The seeded approval table holds the discounted quote for human review.
5. **Christmas 2026** and **New Year 2027** are illustrative dated promotions. The page disables them outside their windows; the backend checks the dates again.

The result has separate quote items, each item's selected term and recurring/one-time price, a monthly total, a simple term commitment estimate, matching rule IDs and approval state. The estimate assumes unchanged monthly charges for each selected term. It does not implement scheduled annual increases, proration, tax, credit checks or live network feasibility.

## Configurable data

| File | Current role |
| --- | --- |
| [catalogue.json](catalogue.json) or a saved catalogue draft | Active offerings and the PO → composite PS → leaf PS → CFS references. Seed: Mobile Mini, Mobile Plus and Extra SMS. |
| [customers.json](customers.json) | One explicitly fictional UK sample, Jason Smith. His mobile number uses Ofcom's reserved drama range and email uses `example.com`. Customer records can later be connected to a dedicated onboarding step. |
| [cpq_policy.json](cpq_policy.json) | Rows for monthly price by offering and contract months, product incompatibility/dependency rules and dated promotions. New offerings without term rows use a 12-month term and their catalogue price. |
| [business_rules.json](business_rules.json) or saved rules | Shared eligibility, conditional price, discount and approval tables. CPQ supplies each item's term and the chosen customer's segment. A configured price row can override the term price. |

Changing a term price, promotion window or product pair in the policy file changes the next quote without a Python edit or restart. Policy edits currently have no business-user editor or publication workflow; the **Business rules** screen edits the four shared decision tables. Prices and percentages use GBP `Decimal` arithmetic and are validated before use.

Local mode stores customer, quote and POC order data in files on this computer. Cloud mode stores records in a private Google Cloud Storage bucket and requires Cloud Run IAM access through an authenticated proxy. A newly created offering starts in **Draft** and cannot appear in CPQ or be quoted. **Publish offer** saves pending catalogue edits, checks the PS-to-CFS realization, and changes the saved status to **Active**. CPQ fetches the current Active offers when opened. **Retire offer** removes the offering from new quotes while leaving prior order records available. Published or retired offers cannot be deleted through the catalogue save API; retired offers cannot be republished. Use fictional records for demonstration. A customer consent workflow and role-specific access remain future work. The [order journey](ORDER.md) persists validated quote snapshots and technical POC orders; it does not create an accepted legal agreement or provision a network.

## TM Forum mapping

- [TMF620 Product Catalog](https://www.tmforum.org/open-digital-architecture/open-apis/product-catalog-management-api-TMF620/v5.0) and the [SID Product Offering Terms model](https://www.tmforum.org/Browsable_HTML_SID_v22.0/html/EARoot/EA2/EA3/EA5/EA1/EA959.htm) inform the offering, term and price distinction. A selected commitment can change the offer price.
- [TMF629 Customer Management](https://www.tmforum.org/open-digital-architecture/open-apis/customer-management-api-TMF629/v5.0) informs the customer resource. The prototype uses a compact fictional customer record stored locally or in the private cloud state bucket; a production SID/Open API mapping would separate the customer role, individual party and contact/address resources.
- [TMF760 Product Configuration](https://www.tmforum.org/open-digital-architecture/open-apis/product-configuration-management-api-TMF760/v5.0) describes using catalogue, policy and inventory context to guide combinations and prices. The POC configuration check implements a small subset; it does not expose TMF760 Query/Check endpoints.
- [TMF679 Product Offering Qualification](https://www.tmforum.org/open-digital-architecture/open-apis/product-offering-qualification-api-TMF679/v5.0) informs commercial eligibility. The shared eligibility table currently checks the customer segment; qualification against inventory, credit or coverage is not connected.
- [TMF671 Promotion Management](https://www.tmforum.org/resources/specification/tmf671-promotion-api-user-guide-v4-1-0/) distinguishes a promotion definition from applying it. The dated definitions are part of the application policy; CPQ applies them and routes the resulting discount through the approval table.
- [TMF648 Quote Management](https://www.tmforum.org/open-digital-architecture/open-apis/quote-management-api-TMF648/v4.0) informs the quote, quote items, party reference and prices. The generated JSON is **TMF-shaped**, with local fields such as `termMonths` and `pricingDecision`; it is not asserted to pass TMF648 conformance tests.
- [TMF663 Shopping Cart](https://www.tmforum.org/resources/specification/tmf663-shopping-cart-management-api-user-guide-v5-0-0/) informs the idea of collecting several items and totaling recurring and one-time charges before checkout. This form does not persist a shopping cart.

The public example mobile number range comes from [Ofcom's numbers for drama](https://www.ofcom.org.uk/phones-and-broadband/phone-numbers/numbers-for-drama).

## Next integration boundary

The current compatibility rules evaluate selected items in one quote. A real multi-line customer journey also needs line or group identity and the customer's product inventory, so a second primary plan on a different line can be handled correctly. The CPQ flow is deployed on private Cloud Run; see [DEPLOYMENT.md](DEPLOYMENT.md) for access and the live test.
