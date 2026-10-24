"""TMF622-style product order and PS-to-CFS orchestration payloads for the POC."""

import copy
from datetime import datetime, timezone

from catalogue_core import ValidationError, validate_catalogue


def _order_prices(prices):
    result = []
    for row in prices:
        price = copy.deepcopy(row["price"])
        price["@type"] = "Price"
        converted = {"@type": "OrderPrice", "priceType": row["priceType"], "price": price}
        if row["priceType"] == "recurring":
            converted["recurringChargePeriod"] = "month"
        result.append(converted)
    return result


def product_order_payload(quote_result, customer, catalogue):
    if quote_result.get("status") != "VALIDATED" or quote_result.get("approval", {}).get("required"):
        raise ValidationError("Only a validated quote without pending approval can be submitted")
    quote = quote_result["quote"]
    validate_catalogue(catalogue, allow_drafts=True)
    offers = {row["id"]: row for row in catalogue["productOfferings"]}
    items = []
    for item in quote["quoteItem"]:
        offer = offers[item["productOffering"]["id"]]
        characteristics = [{"name": row["name"], "value": row["value"], "@type": "NumberCharacteristic"}
                           for row in item["product"]["productCharacteristic"]]
        items.append({"id": item["id"], "@type": "ProductOrderItem", "action": "add", "state": "acknowledged", "quantity": 1,
                      "productOffering": {"id": offer["id"], "name": offer["name"], "@type": "ProductOfferingRef"},
                      "product": {"@type": "Product", "productSpecification": {
                          "id": offer["productSpecification"]["id"], "@type": "ProductSpecificationRef"},
                          "productCharacteristic": characteristics},
                      "itemTerm": [{"@type": "OrderTerm", "duration": {"amount": item["termMonths"], "units": "month"}}],
                      "itemPrice": _order_prices(item["itemPrice"])})
    return {"@type": "ProductOrder", "category": "POC mobile order",
            "description": "Illustrative order request from a validated CPQ quote; no network activation",
            "externalId": [{"id": quote["id"], "owner": "BSS Agent POC", "@type": "ExternalIdentifier"}],
            "quote": [{"id": quote["id"], "@type": "QuoteRef"}],
            "relatedParty": [{"role": "Customer", "@type": "RelatedPartyRefOrPartyRoleRef",
                              "partyOrPartyRole": {"id": customer["id"],
                                                  "name": f"{customer['givenName']} {customer['familyName']}",
                                                  "@type": "PartyRoleRef", "@referredType": "Customer"}}],
            "productOrderItem": items,
            "orderTotalPrice": _order_prices(quote["quoteTotalPrice"])}


def service_order_payload(product_order, catalogue):
    """Resolve each ordered composite PS to its leaf PS and mapped CFS actions."""
    validate_catalogue(catalogue, allow_drafts=True)
    offers = {row["id"]: row for row in catalogue["productOfferings"]}
    specs = {row["id"]: row for row in catalogue["productSpecifications"]}
    services = {row["id"]: row for row in catalogue["serviceSpecifications"]}
    order_items = []
    for product_item in product_order["productOrderItem"]:
        offer = offers[product_item["productOffering"]["id"]]
        bundle = specs[offer["productSpecification"]["id"]]
        for leaf_ref in bundle["bundledProductSpecification"]:
            leaf = specs[leaf_ref["id"]]
            for sid in leaf["serviceSpecificationIds"]:
                cfs = services[sid]
                order_items.append({"id": f"{product_item['id']}-{leaf['id']}-{sid}", "action": "add",
                                    "productOrderItem": {"id": product_item["id"]},
                                    "service": {"@type": "Service", "serviceSpecification": {
                                        "id": sid, "name": cfs["name"], "@type": "ServiceSpecificationRef"},
                                        "serviceCharacteristic": [{"name": leaf["characteristic"],
                                                                   "value": leaf_ref["value"], "unit": leaf["unit"]}]},
                                    "proposedFulfilment": {"targetSystem": cfs["targetSystem"],
                                                            "operation": cfs["operation"],
                                                            "value": leaf_ref["value"], "unit": cfs["unit"]}})
    return {"@type": "ServiceOrder", "state": "acknowledged",
            "productOrder": {"id": product_order["id"]}, "orderItem": order_items,
            "note": [{"text": "CFS orchestration proposal only; no RFS selection or network provisioning."}]}


def next_mobile_order_id(existing_ids, created_at):
    """Allocate a readable UTC reference from the persisted orders in this minute."""
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("Order creation time must include a timezone")
    utc_time = created_at.astimezone(timezone.utc)
    prefix = f"MOB-{utc_time:%H%M}-{utc_time:%d%m%Y}-"
    previous = (int(order_id[len(prefix):]) for order_id in existing_ids
                if order_id.startswith(prefix) and order_id[len(prefix):].isascii()
                and order_id[len(prefix):].isdecimal())
    return f"{prefix}{max(previous, default=0) + 1:04d}"


def create_order(quote_result, customer, catalogue, *, order_id, created_at=None):
    request_payload = product_order_payload(quote_result, customer, catalogue)
    created_at = created_at or datetime.now(timezone.utc)
    product_order = {**copy.deepcopy(request_payload), "id": order_id,
                     "href": f"/tmf-api/productOrderingManagement/v5/productOrder/{order_id}",
                     "state": "acknowledged", "creationDate": created_at.astimezone(timezone.utc).isoformat()}
    service_order = service_order_payload(product_order, catalogue)
    return {"productOrder": product_order, "serviceOrder": service_order,
            "quote": copy.deepcopy(quote_result["quote"]), "customer": copy.deepcopy(customer),
            "contractReview": contract_review()}


def contract_review():
    """Disclosures missing from the demo prevent claiming a binding UK contract."""
    gaps = [
        "Provider legal identity, registered address and contact details are not configured.",
        "VAT-inclusive prices and any taxes are not configured.",
        "Out-of-bundle, roaming and other additional charges are not configured.",
        "Cancellation, cooling-off and early termination terms are not configured.",
        "Complaints and alternative dispute resolution details are not configured.",
        "Service activation date, quality commitments and renewal terms are not configured.",
    ]
    return {"status": "DRAFT_INFORMATION_INCOMPLETE", "bindingContractReady": False,
            "missingDisclosures": gaps,
            "priceChangePolicy": "No in-contract rise is modelled in this POC; do not infer a provider commitment."}
