# Configurable business rules

The local and cloud UI execute **decision tables** for eligibility, prices, discounts and approvals. Conditions and outcomes are data; a generic Python interpreter evaluates them. Adding rows, changing values or adding customer input columns does not require changing Python or restarting the server.

This is the first executable slice of the [72-rule design library](catalogue_design/README.md). Contract schedules, service cardinalities, device matrices, charging balances and all other rule families in that library are not yet executable decision tables.

## Use the editor

1. Open the cloud UI through the authenticated proxy in [README.md](README.md), or start local mode, then open **Business rules**.
2. Choose **Prices**, **Eligibility**, **Discounts** or **Approvals**. Add or edit rows, their conditions, priority, outcome and effective dates.
3. To introduce an input such as contract length, expand **Input columns**, choose **Add input column**, and set the key, label, type and optional default. A column with customer input key `contractMonths` reads `request.context.contractMonths` and appears automatically in **Customer request**.
4. Choose **Keep changes** in the editor and then **Save rules**. Keep changes alone only edits the page's unsaved copy. Reloading discards unsaved edits.
5. Open **Customer request**, supply the relevant inputs, choose an Active offer and preview. The result shows the matched row and explanation for every table, plus the saved rules version.

For example, add a numeric `contractMonths` input and a Prices row with these conditions and output:

| Offering ID | Contract months | Monthly price | Setup price | Priority |
| --- | --- | --- | --- | --- |
| equals `po-mobile-mini` | equals `24` | £15.00 | £0.00 | 100 |

This is an illustrative override, not a seeded tariff. The offering's price is the fallback when no price row matches. Rules use GBP and pre-tax amounts in the current prototype.

## Execution semantics

The order for each selected offer is **eligibility → price → discount → approval**.

| Table | Outcome | Seed behavior |
| --- | --- | --- |
| Eligibility | Eligible / ineligible | Customer segment must be in the offering's allowed segments; otherwise ineligible. |
| Prices | Monthly and setup price | Use the offering's catalogue prices. Conditional rows can override them. |
| Discounts | Percentage, 0–100 | No automatic discount. The effective percentage is the larger of the configured and requested discounts; percentages do not stack. Only recurring charges are discounted. |
| Approvals | Proceed / human review / reject | Any positive effective discount or requested exception requires human review. Other quotes proceed. |

- All conditions on a row are combined with **AND**. Use separate rows for alternatives, with priorities that avoid overlapping matches. An empty condition list means always match.
- Higher numeric priority wins. Two matching rows at the winning priority are an error, even if their outputs agree. File order never breaks ties.
- A disabled row does not apply. If nothing matches, the table fallback applies.
- Missing data that could change the winning decision blocks the quote with a named missing-input error. A row disproved by another AND condition does not block unrelated customers.
- Effective start is inclusive and end is exclusive. Dates use midnight UTC; timestamps must include a timezone. These windows select a rule at quote time. They do **not** yet generate future contractual price schedules or implement anniversary calculations.
- Numeric calculations use Python `Decimal`. Monetary outputs and percentages support up to two decimals. Recurring discounts are rounded once per quote item, then item totals are summed.
- Human review produces a pending quote and no product/service order. Approval reuses the original catalogue, proposal, rules and quote-time snapshots, so a later rules edit does not silently reprice it or apply the discount twice.
- A policy rejection or failed eligibility cannot be overridden by the approval helper. The UI previews review holds; it has no human approval inbox yet.

## Columns and operators

Columns have an ID, display label, type, source and optional default. Supported types are `string`, `number`, `boolean` and a flat `list`. Sources are allowlisted: selected request attributes, `request.context.<key>`, `offer.<field>`, proposed discount/exception, and the calculated effective discount. That calculated discount is available only to approval conditions.

Operators are `eq`, `ne`, `in`, `notIn`, `gt`, `gte`, `lt`, `lte` and `exists`. Comparisons can use a literal or another compatible column. Ordered comparisons require numeric columns; membership requires a list on the right. The UI accepts comma-separated lists and `true`/`false` boolean condition values. An `exists` condition with value `false` checks for absence.

Adding a condition column requires no schema migration: define its metadata and supply the corresponding value. Renaming a display label also needs no code change. Removing a referenced column or changing it to an incompatible type is rejected when saving. A new customer input is self-reported in this preview; authoritative facts such as verified credit or network feasibility still need trusted backend integrations.

New operators, calculation methods, output types, external data integrations or a genuinely new decision table type require an engine extension. Arbitrary Python, SQL, scripts and model-generated expressions are not executed from the tables.

## Storage, versions and deployment boundary

- [business_rules.json](business_rules.json) is the checked-in seed; [business_rules.py](business_rules.py) is the generic interpreter.
- Local mode saves validated edits to `ui/rules.json`, separate from catalogue changes in `ui/draft.json`. Cloud mode saves the same JSON to a private, versioned Cloud Storage bucket. Each quote reads the saved configuration again.
- Each successful UI save creates a version ID. A stale editor receives HTTP 409 instead of overwriting a newer save. Invalid configurations are rejected without replacing the previous version. The cloud demo runs at most one instance; it is not a distributed publication system.
- Backend results retain the rules version, SHA-256 digest, full snapshot and decision reasons. The commercial UI receives reasons and version, with technical service designs kept out of its response.
- The deployed Pub/Sub function reads the current cloud catalogue and rules from the private state bucket, falling back to the seed files when no edits exist. Role checks beyond Cloud Run invocation, publication approval, audit history and transactional version activation remain future work.

Tests cover saved configuration changes taking effect on the next quote, added input columns, eligibility, price selection, discounts and approval snapshots, missing data, conflicts, effective dates, malformed configurations and stale API writes.
