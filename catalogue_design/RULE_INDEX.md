# Rule template index

Research date: 24 October 2026. All 72 checks are proposed design templates; they are not an implemented rule engine. Source links establish supporting patterns, not universal operator policies. See README.md for bindings and scope.

## CAT — Structure and product relationships

Owner: Product design. Phases: design, configure.

Pattern sources: [S-TMF620](https://github.com/tmforum-apis/TMF620_ProductCatalog/blob/main/TMF620-Product_Catalog_Management-v5.0.0.oas.yaml), [S-TMF760](https://www.tmforum.org/open-digital-architecture/open-apis/product-configuration-management-api-TMF760/v5.0), [S-SF](https://trailhead.salesforce.com/pt-BR/content/learn/modules/interface-implementations-for-industries-cpq-rules/discover-interface-implementations-for-industries-cpq-rules).

| ID | Rule | Check | Failure outcome |
| --- | --- | --- | --- |
| CAT-01 | One root specification | A simple sellable offering references exactly one root PS; a bundle-of-offers uses a separate explicit pattern. | `block` |
| CAT-02 | Valid composition graph | Child references resolve to pinned versions and composition contains no self-reference or cycles. | `block` |
| CAT-03 | Mandatory primary line | The configured subscription has exactly one primary Mobile Line; secondary identities use a separate configured limit. | `block` |
| CAT-04 | Option and characteristic cardinality | Selected quantities and characteristic counts meet their min/max/default and choice-group limits. | `block` |
| CAT-05 | Required capability | A selected component's required capability exists in the order or verified inventory; a voice capability does not imply a purchased UK-minutes bundle. | `block` |
| CAT-06 | Exclusion and recommendation | Reject excluded combinations and multiple selections from a single-choice group; recommendations remain suggestions. | `block` |

## ELI — Commercial eligibility

Owner: Commercial qualification. Phases: discover, qualify, order.

Pattern sources: [S-TMF679](https://www.tmforum.org/open-digital-architecture/open-apis/product-catalog-management-api-TMF679/v5.0), [S-SF](https://trailhead.salesforce.com/pt-BR/content/learn/modules/interface-implementations-for-industries-cpq-rules/discover-interface-implementations-for-industries-cpq-rules), [S-LYCA](https://www.lycamobile.co.uk/en/bundle/national-plus/).

| ID | Rule | Check | Failure outcome |
| --- | --- | --- | --- |
| ELI-01 | Sale lifecycle and date window | The offer is sellable for the interaction date; expiry and retirement block a new sale without disabling an existing contracted service. | `block` |
| ELI-02 | Customer and territory eligibility | Segment, residency and any age or entitlement evidence meet the selected offer's explicit criteria; no universal age threshold is assumed. | `block` |
| ELI-03 | Channel and acquisition cohort | The selected web/store/partner channel and new/existing/port-in customer cohort qualify. | `block` |
| ELI-04 | Credit and payment qualification | Run credit, arrears or payment checks only where the offer requires them; prepaid and postpaid policies can differ. | `needsInformation` |
| ELI-05 | Existing-product prerequisite | A companion benefit or multi-product discount has an eligible active parent product belonging to the correct account. | `block` |
| ELI-06 | Qualification evidence freshness | A missing, pending or expired qualification cannot be treated as qualified; return the reason and a request for evidence. | `needsInformation` |

## DEV — Device and network compatibility

Owner: Service design. Phases: configure, technicalQualify, order.

Pattern sources: [S-TMFC009](https://www.tmforum.org/resources/introductory-guide/tmfc009-service-qualification-v1-1-1/), [S-VF-ONENUMBER](https://www.vodafone.co.uk/mobile/onenumber), [S-GSMA-TS43](https://www.gsma.com/newsroom/gsma_resources/ts-43-service-entitlement-configuration/), [S-EE-TERMS](https://ee.co.uk/why-ee/short-terms).

| ID | Rule | Check | Failure outcome |
| --- | --- | --- | --- |
| DEV-01 | SIM form and device support | The requested physical/eSIM path is supported by the device, operator activation channel and current device matrix. | `block` |
| DEV-02 | Cellular companion support | A watch requesting standalone cellular connectivity is a supported cellular model and can be entitled and activated. | `block` |
| DEV-03 | Platform and OS compatibility | Device brand, OS version and primary/companion pairing meet the versioned compatibility matrix. | `block` |
| DEV-04 | Radio and coverage feasibility | The access technology and required coverage are technically available; a maximum speed cap is not represented as a guaranteed speed. | `needsInformation` |
| DEV-05 | Optional feature eligibility | Visual voicemail, WiFi Calling and similar feature selections meet plan, device and network prerequisites. | `block` |
| DEV-06 | Companion messaging support | Apply device/service-profile restrictions such as unsupported MMS or voice/SMS on a data-only companion. | `block` |

## CON — Commitment, renewal and timing

Owner: Commercial contract. Phases: configure, quote, activate, change.

Pattern sources: [S-TMF620](https://github.com/tmforum-apis/TMF620_ProductCatalog/blob/main/TMF620-Product_Catalog_Management-v5.0.0.oas.yaml), [S-LEBARA-HELP](https://www.lebara.co.uk/en/help.html), [S-EE-END](https://ee.co.uk/help/profile/leaving-ee/end-of-my-plan), [S-EE-LEAVE](https://ee.co.uk/help/profile/leaving-ee/cancel-my-contract-with-ee).

| ID | Rule | Check | Failure outcome |
| --- | --- | --- | --- |
| CON-01 | Commitment and start anchor | Choose an allowed commitment and explicit start event, such as activation; calculate its end from the accepted agreement. | `block` |
| CON-02 | Independent billing and allowance cycles | Keep commitment, billing frequency and allowance validity separate; 30 days does not equal a calendar month. | `block` |
| CON-03 | Renewal consent and funds | Renew only under the accepted renewal policy and payment conditions; declare the insufficient-funds outcome. | `block` |
| CON-04 | Calendar versus anniversary timing | Distinguish fixed calendar price events from months-since-activation events and prevent unintended double application. | `block` |
| CON-05 | Cancellation and notice | Evaluate notice, cancellation rights, contract cohort and permitted remaining-term charges at the effective termination date. | `needsInformation` |
| CON-06 | End-of-commitment behavior | Ending a minimum term follows the agreed rolling, renewal or termination policy and does not automatically disconnect a line. | `block` |

## PRI — Price, tax and future price schedules

Owner: Pricing. Phases: design, quote, bill.

Pattern sources: [S-TMF620](https://github.com/tmforum-apis/TMF620_ProductCatalog/blob/main/TMF620-Product_Catalog_Management-v5.0.0.oas.yaml), [S-OFCOM](https://www.ofcom.org.uk/phones-and-broadband/saving-money/telecoms-price-rises-what-are-your-rights), [S-VF-PLANS](https://www.vodafone.co.uk/sim-only/best-sim-only-deals), [S-LEBARA](https://www.lebara.co.uk/en/best-sim-only-deals.html).

| ID | Rule | Check | Failure outcome |
| --- | --- | --- | --- |
| PRI-01 | Typed money and charge | Every recurring, one-time or usage charge declares currency, tax basis, unit and rounding; money uses decimal arithmetic. | `block` |
| PRI-02 | Disclosed consumer price changes | Applicable new UK consumer core-subscription schedules state exact GBP amounts and dates; exclude inflation/percentage-based scheduled increases for this cohort. | `block` |
| PRI-03 | Unambiguous temporal price | For a given charge component exactly one applicable price wins; reject gaps, overlaps and unresolved same-priority alternatives. | `block` |
| PRI-04 | Proration and first/final bill | Define whether a mid-cycle change is prorated, the day-count basis, charging anchor and rounding boundary. | `block` |
| PRI-05 | Deterministic calculation order | Apply compatible adjustments, caps and tax in a specified sequence and preserve the calculation breakdown. | `block` |
| PRI-06 | Fixed-price and contracted cohort | A no-scheduled-rise policy has no annual increase; a new catalogue price does not silently replace an existing customer's accepted schedule. | `block` |

## PRO — Promotions and discounts

Owner: Commercial promotions. Phases: discover, quote, renew, change.

Pattern sources: [S-LYCA](https://www.lycamobile.co.uk/en/bundle/national-plus/), [S-TMF760](https://www.tmforum.org/open-digital-architecture/open-apis/product-configuration-management-api-TMF760/v5.0), [S-SF](https://trailhead.salesforce.com/pt-BR/content/learn/modules/interface-implementations-for-industries-cpq-rules/discover-interface-implementations-for-industries-cpq-rules).

| ID | Rule | Check | Failure outcome |
| --- | --- | --- | --- |
| PRO-01 | Sale and activation deadlines | The purchase is within the promotion window and activation meets its separate deadline; a visible expired banner cannot qualify. | `block` |
| PRO-02 | Redemption and cohort limits | Enforce new-customer, channel, port-in, previous-customer and per-number/account redemption limits. | `block` |
| PRO-03 | Introductory versus ongoing price | Record the initial price, number of discounted cycles and ongoing price without treating the introductory amount as permanent. | `block` |
| PRO-04 | Promotion stacking | Only allowed promotion combinations stack; mutually exclusive benefits use an explicit winning rule or customer choice. | `block` |
| PRO-05 | Qualifying-product discount | A multi-line or bundle discount states its qualifying product, duration and outcome when that product is removed. | `block` |
| PRO-06 | Trial conversion consent | A trial that becomes paid declares the end date, future charge, required acceptance and cancellation route. | `needsInformation` |

## ALL — Allowances, usage and spend control

Owner: Charging and policy. Phases: configure, quote, activate, usage.

Pattern sources: [S-EE-TERMS](https://ee.co.uk/why-ee/short-terms), [S-VF-SPEND](https://www.vodafone.co.uk/help/account/spend-manager), [S-LYCA](https://www.lycamobile.co.uk/en/bundle/national-plus/).

| ID | Rule | Check | Failure outcome |
| --- | --- | --- | --- |
| ALL-01 | Allowance value and unlimited semantics | Declare finite amount or explicit unlimited mode, unit and applicable fair-use policy; never encode unlimited as a large arbitrary number. | `block` |
| ALL-02 | Allowance reset anchor | Reset on the declared billing/activation/30-day boundary; late events cannot grant the cycle twice. | `block` |
| ALL-03 | Expiry and rollover | Each base, add-on, gifted or promotional bucket has its own expiry and rollover policy. | `block` |
| ALL-04 | Consumption order and rounding | Select an eligible bucket by location, traffic class and priority, with explicit usage rounding and minimum units. | `block` |
| ALL-05 | Exhaustion behavior | Exhaustion follows block, throttle, paid overage or top-up policy; buying a top-up and resetting a cycle restore only authorized entitlement. | `block` |
| ALL-06 | Spend-cap coverage | A spend cap declares which usage and charges it includes and excludes; a zero usage cap does not imply all account charges are zero. | `block` |

## GEO — Destinations, roaming and usage eligibility

Owner: Roaming and charging. Phases: configure, quote, activate, usage.

Pattern sources: [S-EE-TERMS](https://ee.co.uk/why-ee/short-terms), [S-LYCA](https://www.lycamobile.co.uk/en/bundle/national-plus/), [S-ERICSSON-ROAM](https://www.ericsson.com/en/reports-and-papers/ericsson-technology-review/articles/roaming-in-the-5g-system), [S-VF-ONENUMBER](https://www.vodafone.co.uk/mobile/onenumber).

| ID | Rule | Check | Failure outcome |
| --- | --- | --- | --- |
| GEO-01 | Domestic destination classification | Domestic calling/text rules explicitly include eligible number classes and exclude premium or special destinations as configured. | `block` |
| GEO-02 | International destination classification | International minutes from home are restricted by versioned country, number and mobile/landline lists. | `block` |
| GEO-03 | Roaming access versus charging | Roaming access permission on Mobile Line does not imply free usage; eligible voice/SMS/data rating policies must also resolve. | `block` |
| GEO-04 | Zone and roaming cap | Use the selected plan's zone list and roaming cap; an unlimited domestic bucket does not automatically remove the roaming cap. | `block` |
| GEO-05 | Roaming fair-use and duration | Apply the operator's stable-link, permanent-roaming and usage-window policy, with required evidence and notices. | `needsInformation` |
| GEO-06 | Companion roaming eligibility | A companion's roaming eligibility follows the device and selected service profile rather than inheriting every primary-line capability. | `block` |

## SHA — Shared allowance and multi-SIM

Owner: Sharing service and charging. Phases: configure, qualify, activate, usage, change.

Pattern sources: [S-EE-GIFT](https://ee.co.uk/help/mobile/manage-use/pay-monthly/data-gifting), [S-EE-TERMS](https://ee.co.uk/why-ee/short-terms), [S-VF-ONENUMBER](https://www.vodafone.co.uk/mobile/onenumber), [S-GSMA-TS43](https://www.gsma.com/newsroom/gsma_resources/ts-43-service-entitlement-configuration/).

| ID | Rule | Check | Failure outcome |
| --- | --- | --- | --- |
| SHA-01 | Account ownership and authority | Donor, recipient and sharing-group membership meet account ownership and authorized-user rules. | `block` |
| SHA-02 | Mode-specific member eligibility | Gift, pooled allowance and companion modes use different eligible member classes; an operator may exclude watches from gifting while supporting companion sharing. | `block` |
| SHA-03 | Transfer amount and limits | Gift amount meets quantum/min/max and unreserved donor balance; enforce cycle caps without interpreting unlimited as transferable infinity. | `block` |
| SHA-04 | Atomic conservation and expiry | A gift debits and credits the same units atomically, applies the declared expiry and handles retry/concurrent requests once. | `block` |
| SHA-05 | Companion identity and number association | Companion activation binds its own subscription identity to the correct primary group; number sharing is optional and separate from allowance sharing. | `block` |
| SHA-06 | Group policy inheritance | Declare which bars/entitlements propagate across members, SIM-specific exceptions and maximum member count. | `block` |

## MAP — PS-to-CFS realization and dependencies

Owner: Service design and orchestration. Phases: design, decompose, activate, change.

Pattern sources: [S-SID](https://www.tmforum.org/Browsable_HTML_SID_R20.0/content/_3E3F0EC000E93ED67838027E-content.html), [S-TMF633](https://github.com/tmforum-apis/TMF633_ServiceCatalog/blob/master/TMF633-ServiceCatalog-v4.0.0.swagger.json), [S-TMFC009](https://www.tmforum.org/resources/introductory-guide/tmfc009-service-qualification-v1-1-1/).

| ID | Rule | Check | Failure outcome |
| --- | --- | --- | --- |
| MAP-01 | Service instance identity and reuse | Reuse is scoped by service specification plus line/account/group identity; two PSs do not create duplicate voice or line CFSs, and two different lines are never merged. | `block` |
| MAP-02 | Characteristic transforms and conflicts | Map commercial values into typed service characteristics with explicit units and merge strategies; conflicting permissions or values require resolution. | `block` |
| MAP-03 | Dependency graph and inventory reuse | Order required CFSs before dependants; verified existing services can satisfy dependencies; reject cycles and unresolved references. | `block` |
| MAP-04 | Commercial-only versus service change | A price/commitment-only change does not reprovision the network; an entitlement change amends the existing CFS at the agreed effective time. | `block` |
| MAP-05 | Technical solution qualification | Choose a feasible RFS solution through technical qualification before activation; qualification alone does not allocate a resource. | `needsInformation` |
| MAP-06 | Shared service release | Removing one commercial component only removes its owned entitlement; keep a shared CFS while other products or dependants require it. | `block` |

## CHG — Changes, migration and termination

Owner: Product and service order management. Phases: configure, order, change.

Pattern sources: [S-TMF620](https://github.com/tmforum-apis/TMF620_ProductCatalog/blob/main/TMF620-Product_Catalog_Management-v5.0.0.oas.yaml), [S-TMF633](https://github.com/tmforum-apis/TMF633_ServiceCatalog/blob/master/TMF633-ServiceCatalog-v4.0.0.swagger.json), [S-EE-END](https://ee.co.uk/help/profile/leaving-ee/end-of-my-plan), [S-EE-LEAVE](https://ee.co.uk/help/profile/leaving-ee/cancel-my-contract-with-ee).

| ID | Rule | Check | Failure outcome |
| --- | --- | --- | --- |
| CHG-01 | Allowed transitions | Add, amend, suspend, resume, migrate and remove follow the offer/service lifecycle and published migration paths. | `block` |
| CHG-02 | Commitment impact of change | Declare whether the change preserves or restarts commitment and whether charges apply; obtain required acceptance. | `needsInformation` |
| CHG-03 | Effective change boundary | Upgrades, downgrades and allowance changes use immediate, requested-date or next-cycle timing with explicit unused-balance treatment. | `block` |
| CHG-04 | Port-in and SIM replacement identity | Number porting or SIM replacement preserves the correct subscription/product identity and retires the replaced resource without duplicating the purchase. | `block` |
| CHG-05 | Parent and member removal | Deleting a primary line or qualifying product first resolves companion memberships, dependent services and conditional discounts. | `block` |
| CHG-06 | Concurrent change and revalidation | Revalidate against current inventory before submission, reject stale changes and apply each authorized change once. | `block` |

## GOV — Publication, approvals, audit and federation

Owner: Catalogue governance. Phases: design, publish, quote, order, sync.

Pattern sources: [S-TMF620](https://github.com/tmforum-apis/TMF620_ProductCatalog/blob/main/TMF620-Product_Catalog_Management-v5.0.0.oas.yaml), [S-TMF760](https://www.tmforum.org/open-digital-architecture/open-apis/product-configuration-management-api-TMF760/v5.0), [S-SID](https://www.tmforum.org/Browsable_HTML_SID_R20.0/content/_3E3F0EC000E93ED67838027E-content.html).

| ID | Rule | Check | Failure outcome |
| --- | --- | --- | --- |
| GOV-01 | Approved publication | A revision is publishable only with complete mappings, required source evidence, ownership, checks and an approval record. | `block` |
| GOV-02 | Federated source integrity | Imports preserve source identity/version, reject stale updates and unresolved dependencies, and reconcile conflicts before publication. | `block` |
| GOV-03 | Human commercial exception | Discounts and commercial exceptions need an authorized decision; approval cannot waive hard compatibility, ownership or regulatory constraints. | `needsApproval` |
| GOV-04 | Reproducible decision snapshot | Pin catalogue/rule/price/zone/device-matrix versions, timestamps and accepted contract terms; never silently reprice a saved accepted contract. | `block` |
| GOV-05 | Explainability and notification | Return rule IDs, reasons, required information and applicable price/renewal/expiry notices without exposing technical service detail to product managers. | `needsInformation` |
| GOV-06 | Deterministic activation of rules | Apply the accepted version at its effective event once; support replay, conflict detection and compensation for partial operations; model output cannot override the rules. | `block` |

