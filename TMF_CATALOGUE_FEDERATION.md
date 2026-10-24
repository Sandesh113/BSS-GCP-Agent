# Catalogue federation research and design

Research date: 21 October 2026. This is a design decision for the GCP demo, not a claim of TM Forum API conformance.

## Entity model

TMF620 Product Catalog Management v5 defines `ProductOffering`, `ProductSpecification`, prices, catalogues, categories, import/export jobs and hub events. A ProductOffering references one ProductSpecification. For Mobile Mini, that specification is a composite (`isBundle: true`) with `bundledProductSpecification` references to Voice, Data and SMS. Their allowance characteristics are configured in the offer or order context. A ProductSpecification has `serviceSpecification` references to the CFS specifications exposed by TMF633 Service Catalog Management v4. SID names the relationship `ProductSpecRealizedAsCFSSpec`. Our service actions are design metadata; actual HSS, packet gateway and SMSC commands require separate fulfillment adapters.

## Federation and sync

The source catalogue owns its entities. A remote catalogue is a read model with mappings from `(source system, source ID, source version)` to a local ID. Onboarding takes a full snapshot first, then subscribes to TMF620 `/hub` and TMF633 `/hub` events. The TMF620 v5 OAS exposes `/importJob` and `/exportJob` task resources for bulk transfer, as well as `/hub` for event subscriptions. The TMF633 v4 specification also has import/export task resources and event notifications. A periodic reconciliation job polls the source API with pagination and checks versions or content hashes, because events can be missed or delivered more than once. Imported records stay in draft until all references resolve and validation passes; publication swaps a versioned, immutable catalogue snapshot for the quote processor.

TMF620 includes `lifecycleStatus` on Product Offerings. This POC uses the local statuses **Draft → Active → Retired**. Publication is an explicit validated action; only Active offerings enter CPQ or the agent quote path. Retirement stops new sales without deleting stored orders. These three labels and transitions are our implementation policy, not a claim that TMF620 mandates this exact enumeration. TMF620 v5 also distinguishes sales actions and their validity from the general `validFor` period; scheduling future launches is outside this POC. See the [TMF620 API](https://www.tmforum.org/open-digital-architecture/open-apis/product-catalog-management-api-TMF620/v5.0) and the [TM Forum lifecycle discussion](https://engage.tmforum.org/discussion/tmf-620-product-offering-lifecycle-states-validity-period).

Sync sequence:

1. Configure a source with base URL, authentication secret, supported API version, mapping policy and ownership scope.
2. Run source export/destination import jobs when the source supports them, or page through catalogue resources. Ingest TMF633 service specifications before TMF620 product specifications, offering prices, and offerings.
3. Normalize and validate IDs, versions, lifecycle status, currency, references, characteristic units, and price values. Keep provenance (`source`, `sourceId`, `sourceVersion`, `lastSeen`, `contentHash`).
4. Apply create/update/retire events idempotently to a staging revision. Reject stale events. Do not delete an offering referenced by an existing quote or order.
5. Reconcile on a schedule; produce a diff for review. Publish only a complete consistent revision. Every quote stores the exact catalogue snapshot/version used for audit and approvals.

The UI should show source, version, sync health, unresolved references and a diff before publication. Manual catalogue edits should be separate from imported source-owned records; conflicts require an explicit override policy. An outbound TMF620 facade can expose published offerings and specs, with proper pagination, filtering, PATCH semantics and events as a later conformance phase. A similarly separate TMF633 facade exposes CFS specifications. The internal demo JSON is **TMF-shaped**, not a compliant TMF620 or TMF633 API.

## Primary sources

- TM Forum [TMF620 v5 API page](https://www.tmforum.org/open-digital-architecture/open-apis/product-inventory-management-api-TMF620/v5.0) and [v5 OpenAPI](https://github.com/tmforum-apis/TMF620_ProductCatalog/blob/main/TMF620-Product_Catalog_Management-v5.0.0.oas.yaml).
- TM Forum [TMF633 v4 API page](https://www.tmforum.org/open-digital-architecture/open-apis/service-catalog-management-api-TMF633/v4.0).
- TM Forum [TMF633 v4 OpenAPI](https://github.com/tmforum-apis/Open_Api_And_Data_Model/blob/master/apis/TMF633_Service_Catalog/swaggers/TMF633-ServiceCatalog-v4.0.0.swagger.json).
- TM Forum SID [ProductSpecification to CustomerFacingServiceSpec relationship](https://www.tmforum.org/Browsable_HTML_SID_R20.0/content/_3E3F0EC000E93ED67838027E-content.html).
- TM Forum community [composite ProductSpecification and bundledProductSpecification discussion](https://engage.tmforum.org/discussion/tmf620-productofferingtermproductspecification).
- TM Forum community [TMF620 ExportJob/ImportJob catalogue transfer discussion](https://engage.tmforum.org/discussion/tmf620-and-billing-catalogue).
