# Modular mobile catalogue rules

Research date: **24 October 2026**. This is the first reference library for the agreed **one simple Product Offering -> one composite PS -> ten child PS -> seven reusable CFSS** design. The files are draft design assets; the current quote service does not load them. Operator examples demonstrate possible rules, not universal policies or published internal operator CFS models.

The separate [runtime decision tables](../BUSINESS_RULES.md) now implement configurable eligibility, prices, discounts and approvals in the local preview. They are the first executable slice of this design; the 72 templates below remain a broader implementation backlog.

## The reusable assets

| File | Purpose |
| --- | --- |
| [rule_library.json](rule_library.json) | 72 rule templates in 12 families, with ownership, execution phase, parameters, expected failure outcomes and source references. |
| [RULE_INDEX.md](RULE_INDEX.md) | Readable index of every rule template. |
| [building_blocks.json](building_blocks.json) | Ten PS, seven CFSS, instance-reuse keys, dependencies, an offer/composite template and three illustrative price policies. |
| [worked_examples.json](worked_examples.json) | 18 design scenarios showing expected decisions and four exact price lookups. |
| [sources.json](sources.json) | 20 primary public sources, what they support and relevant limitations. |
| [check_design.py](check_design.py) | Checks reference integrity, service dependency cycles, temporal price continuity and the four price lookups. It does not execute the 72 rules. |

## Put the rule with the entity that owns the decision

Contract duration and annual price changes principally belong to the **offering, price policy and accepted agreement**, rather than every leaf PS. A leaf PS describes a capability and its configurable values. Product relationships constrain combinations. Service relationships describe realization and operational dependencies. Usage policies are provisioned into charging/policy functions, which enforce them during consumption.

| Scope | Rule examples | Likely TM Forum representation / boundary |
| --- | --- | --- |
| Offering / price | Contract options, selling dates, channel, price, intro duration, dated future charges | TMF620 `ProductOffering`, `ProductOfferingTerm`, `ProductOfferingPrice`, validity and price-policy references. |
| PS and characteristics | Data amount/unit, speed tier, configurable/default values, allowed ranges | TMF620 specification/characteristic definitions and offering value restrictions. |
| PS-to-PS | Requires, excludes, recommends, choices and conditional selection | Specification relationships plus explicit configuration rules. Optional child selection is an application extension, not a fabricated field on `bundledProductSpecification`. |
| Customer/context | New/existing customer, segment, channel, existing products, qualification evidence | TMF679 commercial qualification pattern. |
| Configuration | Options, compatible values, min/max and calculated prices | TMF760 configuration pattern using catalogue, policies and inventory. |
| PS-to-CFSS | Characteristic transforms, shared CFS instance resolution, entitlement ownership | SID realization association and TMF620 service-spec references; mapping behavior is our application design. |
| CFSS-to-CFSS | Required parent line, voicemail voice dependency, group membership | TMF633 service relationships; lifecycle sequencing and conflict handling need implementation. |
| Technical solution | Device/network availability and feasible underlying RFS/resources | TMF645 / TMFC009 qualification; qualification checks availability without allocating resources. |
| Accepted product/service | Pinned prices, term, source rule versions and line/group identities | Persist the accepted contract and inventory links; changing the sales catalogue does not silently change them. |
| Usage / balances | Reset, expiry, overage, spend cap, data transfer | Charging/policy/balance services consume versioned definitions. The quote engine is not a real-time balance ledger. |

These APIs describe interfaces and data patterns. They do not prescribe one universal executable language for every rule above. Our versioned rule definitions need deterministic application logic behind those interfaces.

## The 12 rule families

| Family | Six reusable rules |
| --- | --- |
| CAT — Structure | One root PS; valid composition graph; one mandatory primary line; cardinalities; required capabilities; exclusions and suggestions. |
| ELI — Eligibility | Sale lifecycle/window; customer/territory; channel/cohort; required credit/payment checks; existing-product prerequisites; qualification freshness. |
| DEV — Compatibility | SIM/device support; cellular watch; OS/pairing matrix; access/coverage; optional feature support; companion messaging limits. |
| CON — Contract | Commitment/start anchor; distinct billing/allowance cycles; renewal; calendar versus anniversary timing; cancellation/notice; end-of-term behavior. |
| PRI — Pricing | Money/tax/charge type; disclosed price schedule; temporal price selection; proration; calculation order; fixed-price and existing-contract preservation. |
| PRO — Promotions | Sale/activation deadlines; eligibility/redemption; introductory duration; stacking; qualifying-product discount; trial conversion. |
| ALL — Allowances | Explicit unlimited semantics; reset; expiry/rollover; consumption/rounding; exhaustion; spend-cap scope. |
| GEO — Geography | Domestic number classes; international destinations; roaming access versus inclusive charging; roaming zones/caps; fair use; companion roaming. |
| SHA — Sharing | Account authority; mode-specific membership; gift amount/limits; atomic transfer; companion identity; inherited policies/member limit. |
| MAP — Realization | Instance-key reuse; value transforms/conflicts; dependency order; commercial-only changes; technical solution; shared service release. |
| CHG — Change | Allowed transitions; commitment impact; effective timing; port/SIM replacement; parent removal; concurrency/revalidation. |
| GOV — Governance | Approved publication; federated integrity; human exceptions; pinned decisions; reasons/notices; deterministic event application. |

All 72 are **proposed rule templates**. Source references establish the pattern or example behind each family; the precise assertion is our reference design and should not be read as a verbatim operator policy. Publication requires binding values, scope, effective dates, cohort, version and approval.

## Bind rules to our ten PS and seven CFSS

| Child PS | CFS realization | Main rule bindings |
| --- | --- | --- |
| Mobile access | Mobile Line | Mandatory primary; optional secondary identities; SIM/access compatibility; roaming profile. |
| UK voice | Mobile Voice | Domestic destinations; finite/unlimited minutes; reset, rating and rounding. |
| UK SMS | Mobile SMS | Eligible number classes; message count; expiry and overage. |
| UK data | Mobile Data | Volume, speed, cycle, exhaustion and spend controls. |
| International calling | Reuse Mobile Voice | Country/number-type policy; separate international bucket on the same line. |
| Roaming | Reuse Mobile Line | Access permission; dependent voice/SMS/data policies for included usage and caps. |
| Voicemail | Voicemail | Required voice capability; mailbox/visual feature eligibility. |
| MMS | Mobile MMS | MMS platform/bearer feasibility; messaging allowance; device restrictions. |
| Smartwatch | Shared Allowance / Multi-SIM | Eligible primary product, own companion identity, device entitlement and member policies. |
| Data gifting | Reuse Shared Allowance / Multi-SIM | Authorized donor/recipient, gift eligibility, finite transferable balance and expiry. |

Mobile Line has **exactly one primary per subscription group**; optional companion lines have their own configured limit. Voice, SMS, data, voicemail and MMS are generally `0..1` per applicable line. Sharing is `0..1` per group, with several member lines. A particular offering can require otherwise optional capabilities.

Two useful refinements prevent incorrect pairings:

- **International calling requires voice capability, not necessarily the purchase of a UK-minutes bucket.** The service dependency can supply voice while the domestic allowance PS is unselected.
- **MMS requires its technical messaging/data bearer, not automatically a retail UK data allowance.** Technical dependencies should not force an unrelated commercial purchase.

The common Sharing CFSS has `gift`, `pool` or `companion` modes. Each mode selects a different policy set. Same CFSS does not mean the same member rules or the same service instance. Use `(accountId, sharingGroupId)` as its instance key; use `(subscriptionId, lineId)` for line services. Number sharing and allowance sharing are independent characteristics.

## Contract length and price timing

Use three different clocks: **minimum commitment**, **billing cycle** and **allowance validity**. A 12-month agreement can bill monthly while an add-on lasts until the next renewal. A 30-day plan and a calendar-month plan produce different boundaries.

The illustrative policies in `building_blocks.json` start on 24 October 2026, have a 24-month commitment, and quote tax-inclusive GBP prices:

| Policy | Until 31 March 2027 | From 1 April 2027 | From 24 October 2027 | From 1 April 2028 |
| --- | --- | --- | --- | --- |
| Fixed | £20.00 | £20.00 | £20.00 | £20.00 |
| Calendar change | £20.00 | £22.50 | £22.50 | £25.00 |
| Anniversary change | £20.00 | £20.00 | £22.50 | £22.50 |

These are invented demonstration amounts, not live operator tariffs. Choose one policy; do not accidentally run both annual mechanisms. An introductory discount ending is another explicit event, with a declared order if it coincides with a scheduled change.

[Ofcom's current guidance](https://www.ofcom.org.uk/phones-and-broadband/saving-money/telecoms-price-rises-what-are-your-rights) requires applicable new UK consumer core-subscription increases to be disclosed upfront as pounds-and-pence amounts with timing. Store that schedule in the accepted quote/agreement. Existing/older or business contracts require their own policy cohort. Do not put a universal unknown CPI-plus-percentage increase into the new-consumer default. No annual rise is also a valid policy.

A calendar boundary uses an explicit time zone; a schedule has continuous, non-overlapping intervals with an inclusive start and exclusive end. Billing needs an approved proration convention. A price-only event changes billing; it does not activate another Mobile Line or update network allowances.

## Evidence that affects our defaults

| Observed source | Rule implication |
| --- | --- |
| [EE short terms](https://ee.co.uk/why-ee/short-terms) and [gifting help](https://ee.co.uk/help/mobile/manage-use/pay-monthly/data-gifting) | Gift modes need account/member constraints. Published gift-cap descriptions differ, so the precise cap needs cohort/version review before publication. |
| [Vodafone OneNumber](https://www.vodafone.co.uk/mobile/onenumber) | Companion profiles may restrict MMS, roaming and bars even while allowances are shared. |
| [Vodafone Spend Manager](https://www.vodafone.co.uk/help/account/spend-manager) | Spend-control policy must identify covered and excluded charge classes. |
| [Lyca National Plus](https://www.lycamobile.co.uk/en/bundle/national-plus/) | On the research date its visible promotional terms ended on 23 October 2026. The stale banner is a real example for blocking expired sales. |
| [Lebara help](https://www.lebara.co.uk/en/help.html) | Renewal funding and opt-out rules differ from commitment length and service expiry. |
| [EE end of plan](https://ee.co.uk/help/profile/leaving-ee/end-of-my-plan) | Commitment expiry does not itself mean network disconnection. |

## A reusable rule card and pairing behavior

Each published rule instance needs a stable ID/version, business owner, subject scope, phase, parameters, effective dates/cohort, input evidence, failure/unknown outcomes, priority, source and approval record. Templates in `rule_library.json` contain the reusable checks; an offer binds the parameters. Do not embed arbitrary model-generated code in a policy definition.

For example, binding `SHA-03` to a gift profile supplies a quantum, cycle limit and donor-balance evidence. The common CFS then invokes a balance-transfer operation. Binding companion rules to the same CFSS supplies a compatible-device matrix, secondary-line identity and inherited-bar policy. It invokes companion activation instead.

| Relationship | Example | Behavior |
| --- | --- | --- |
| `requires` | Voicemail -> Mobile Voice | Block or derive an explicitly permitted dependency; show any extra charge before acceptance. |
| `excludes` | Incompatible device/profile | Block with a useful reason. |
| `recommends` | Optional travel add-on | Suggest without silently purchasing it. |
| `oneOf` | One SIM form per line profile | Enforce exactly one choice when required. |
| `limits` | Sharing group -> member count | Enforce the operator/cohort value. |
| `realizes/reuses` | UK voice + International -> same Voice CFSS | Merge distinct buckets onto the same line-scoped service. |
| `amends` | Roaming -> Mobile Line | Change an existing profile; resolve associated usage policies. |
| `inherits` | Companion -> primary policy bars | Propagate selected rules with explicit SIM-specific exceptions. |
| `ownsEntitlement` | Domestic PS -> domestic bucket | Removal releases that bucket while preserving other products' voice service. |

Hard constraints combine by intersection: an offer may narrow a PS range, add mandatory choices and restrict eligibility. It may not silently widen technical limits. Incompatible constraints block publication. Missing evidence yields `needsInformation`; a discount request yields `needsApproval`; a recommendation yields `suggest`. Commercial approval cannot override a hard compatibility or regulatory block.

## Applying the blocks to the GCP agent

1. Publish only a complete, approved immutable catalogue/rule revision.
2. Let the model propose offering IDs and user intent/choices.
3. Use code to resolve eligibility, configuration, prices and any required missing evidence.
4. Show the immediate and future prices, commitment and explanation; obtain applicable acceptance/approval.
5. Revalidate time-sensitive evidence at order submission and merge CFS instances by identity.
6. Send ordered service changes with effective dates and pinned mappings; charging/policy adapters enforce usage rules.

The first implementation slice should cover mandatory line/cardinalities, capability dependencies, device compatibility, expiry/cohort, calendar/anniversary prices, sharing modes, CFS reuse and approvals. Usage ledger enforcement, live technical qualification, contract billing and federation require their own connected adapters; the model should never manufacture a successful check for one of these.

Run the design check from the project root:

```powershell
.venv\Scripts\python.exe catalogue_design/check_design.py
```

The check validates the static reference definitions and four price scenarios. The other scenarios specify expected behavior for future runtime implementation.
