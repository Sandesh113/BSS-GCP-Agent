"""Validated PO -> PS -> CFS catalogue and deterministic quote construction."""
import copy
import json
import math
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from business_rules import RuleError, digest, evaluate_offer, load_rules, validate_rules
from product_constraints import ProductConstraintError, evaluate_constraints

DEFAULT_CATALOGUE = json.loads((Path(__file__).parent / "catalogue.json").read_text(encoding="utf-8"))


class ValidationError(ValueError):
    pass


def money(value):
    try:
        n = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValidationError("invalid price") from exc
    if not n.is_finite() or n < 0 or n > 1000000:
        raise ValidationError("price must be between 0 and 1,000,000")
    return str(n.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def validate_catalogue(catalogue, allow_drafts=False):
    if not isinstance(catalogue, dict) or not catalogue.get("version") or catalogue.get("currency") != "GBP":
        raise ValidationError("catalogue needs version and GBP currency")
    maps = {}
    for key in ("serviceSpecifications", "productSpecifications", "productOfferings"):
        rows = catalogue.get(key)
        if not isinstance(rows, list) or len(rows) > 500:
            raise ValidationError(f"{key} must be a list of at most 500")
        ids = [r.get("id") for r in rows if isinstance(r, dict)]
        if len(ids) != len(rows) or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
            raise ValidationError(f"{key} needs unique nonempty IDs")
        if any(not isinstance(r.get("name"), str) or not r["name"] for r in rows):
            raise ValidationError(f"{key} needs names")
        maps[key] = dict(zip(ids, rows))
    services, specs, offers = (maps[k] for k in ("serviceSpecifications", "productSpecifications", "productOfferings"))
    for service in services.values():
        if any(not isinstance(service.get(k), str) or not service[k] for k in ("targetSystem", "operation", "unit")):
            raise ValidationError(f"{service['id']} needs targetSystem, operation and unit")
    for spec in specs.values():
        if spec.get("isBundle"):
            refs = spec.get("bundledProductSpecification")
            if not isinstance(refs, list) or (not refs and not allow_drafts) or any(not isinstance(r, dict) for r in refs):
                raise ValidationError(f"{spec['id']} needs bundled product specifications")
            ids = [r.get("id") for r in refs]
            if len(ids) != len(set(ids)) or spec["id"] in ids or any(i not in specs or specs[i].get("isBundle") for i in ids):
                raise ValidationError(f"{spec['id']} has duplicate, unknown or nested bundle references")
            for ref in refs:
                value = ref.get("value")
                if (isinstance(value, bool) or not isinstance(value, (int, float))
                        or not math.isfinite(value) or value <= 0 or value > 1000000):
                    raise ValidationError(f"{spec['id']} has invalid allowance")
            continue
        refs = spec.get("serviceSpecificationIds")
        if not spec.get("characteristic") or not spec.get("unit") or not isinstance(refs, list) or (not refs and not allow_drafts):
            raise ValidationError(f"{spec['id']} needs characteristic, unit and CFS references")
        if len(refs) != len(set(refs)) or any(r not in services for r in refs):
            raise ValidationError(f"{spec['id']} has duplicate or unknown CFS references")
        # The allowance value is passed to the CFS unchanged, so 1 TB must never reach a GB service.
        if any(services[r]["unit"] != spec["unit"] for r in refs):
            raise ValidationError(f"{spec['id']} unit must match the unit of its mapped CFS")
    for offer in offers.values():
        if offer.get("lifecycleStatus") not in ("Draft", "Active", "Retired"):
            raise ValidationError(f"{offer['id']} has invalid lifecycle status")
        for k in ("monthlyPrice", "setupPrice"):
            money(offer.get(k))
            if Decimal(str(offer[k])).as_tuple().exponent < -2:
                raise ValidationError(f"{offer['id']} price has more than two decimals")
        segments = offer.get("allowedSegments")
        if not isinstance(segments, list) or not segments or any(s not in ("consumer", "business") for s in segments):
            raise ValidationError(f"{offer['id']} has invalid customer segments")
        ref = offer.get("productSpecification")
        if not isinstance(ref, dict) or ref.get("id") not in specs or not specs[ref["id"]].get("isBundle"):
            raise ValidationError(f"{offer['id']} needs one composite product specification")
        if offer["lifecycleStatus"] == "Active":
            children = specs[ref["id"]]["bundledProductSpecification"]
            if not children or any(not specs[child["id"]].get("serviceSpecificationIds") for child in children):
                raise ValidationError(f"{offer['id']} cannot publish until service realization is mapped")
    return catalogue


def transition_offering(catalogue, offering_id, action):
    """Publish or retire one offering; catalogue validation gates publication."""
    transitions = {"publish": ("Draft", "Active"), "retire": ("Active", "Retired")}
    if action not in transitions:
        raise ValidationError("Unsupported offering lifecycle action")
    offer = next((row for row in catalogue["productOfferings"] if row["id"] == offering_id), None)
    if offer is None:
        raise ValidationError("Product offering not found")
    expected, target = transitions[action]
    if offer["lifecycleStatus"] != expected:
        raise ValidationError(f"{action} requires an offering in {expected} status")
    offer["lifecycleStatus"] = target
    validate_catalogue(catalogue, allow_drafts=True)
    return catalogue


def validate_request(request):
    if not isinstance(request, dict) or any(not isinstance(request.get(k), str) or not request[k].strip() for k in ("requestId", "customerId", "text")):
        raise ValidationError("requestId, customerId and text are required")
    if request.get("segment") not in ("consumer", "business") or len(request["text"]) > 4000:
        raise ValidationError("invalid segment or request text")
    if "context" in request and (not isinstance(request["context"], dict) or len(request["context"]) > 100):
        raise ValidationError("request context must be an object with at most 100 fields")
    return request


def _amount(value):
    return {"dutyFreeAmount": {"value": money(value), "unit": "GBP"}}


def build_result(request, proposal, catalogue=None, rules=None, *, policy=None, as_of=None, _approval_granted=False):
    validate_request(request)
    catalogue = validate_catalogue(copy.deepcopy(catalogue or DEFAULT_CATALOGUE), allow_drafts=True)
    ids = proposal.get("productOfferingIds") if isinstance(proposal, dict) else None
    if not isinstance(ids, list) or not ids or len(ids) > 10 or any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
        raise ValidationError("proposal needs unique productOfferingIds")
    offers = {r["id"]: r for r in catalogue["productOfferings"]}
    specs = {r["id"]: r for r in catalogue["productSpecifications"]}
    services = {r["id"]: r for r in catalogue["serviceSpecifications"]}
    for oid in ids:
        if oid not in offers or offers[oid]["lifecycleStatus"] != "Active":
            raise ValidationError(f"{oid} is not an active offering")
    # Import here because CPQ loads the catalogue engine; both paths use the
    # same versioned product-combination rows.
    from cpq_core import load_policy, validate_policy
    policy = copy.deepcopy(load_policy() if policy is None else validate_policy(policy))
    try:
        evaluate_constraints(ids, policy)
    except ProductConstraintError as exc:
        raise ValidationError(str(exc)) from exc
    try:
        discount = Decimal(str(proposal.get("discountPercent", 0)))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("invalid discount") from exc
    if (not discount.is_finite() or discount < 0 or discount > 100 or discount.as_tuple().exponent < -2
            or not isinstance(proposal.get("exceptionRequested", False), bool)):
        raise ValidationError("invalid discount or exception flag")
    try:
        rules = copy.deepcopy(load_rules() if rules is None else validate_rules(rules))
        decision_time = as_of or datetime.now(timezone.utc)
        if not isinstance(decision_time, datetime) or decision_time.tzinfo is None:
            raise RuleError("Rule evaluation needs a timezone-aware date")
        decisions = {oid: evaluate_offer(rules, request, proposal, offers[oid], decision_time) for oid in ids}
    except RuleError as exc:
        raise ValidationError(str(exc)) from exc
    approval = any(d["requiresApproval"] for d in decisions.values()) and not _approval_granted
    quote_items, service_items = [], []
    monthly = setup = Decimal(0)
    for index, oid in enumerate(ids, 1):
        offer = offers[oid]
        decision = decisions[oid]
        base_monthly = money(decision["monthlyPrice"])
        setup_price = money(decision["setupPrice"])
        monthly_price = money(Decimal(base_monthly) * (Decimal(100) - decision["discountPercent"]) / Decimal(100))
        monthly += Decimal(monthly_price)
        setup += Decimal(setup_price)
        characteristics = []
        bundle = specs[offer["productSpecification"]["id"]]
        for ref in bundle["bundledProductSpecification"]:
            spec = specs[ref["id"]]
            characteristics.append({"name": spec["characteristic"], "value": ref["value"], "unit": spec["unit"],
                                    "productSpecification": {"id": spec["id"], "name": spec["name"]}})
            for sid in spec["serviceSpecificationIds"]:
                service = services[sid]
                service_items.append({"id": f"{index}-{spec['id']}-{sid}", "action": "add",
                                      "service": {"serviceSpecification": {"id": sid, "name": service["name"]},
                                                  "serviceCharacteristic": [{"name": spec["characteristic"], "value": ref["value"], "unit": spec["unit"]}]},
                                      "productOrderItem": {"id": str(index)},
                                      "proposedFulfilment": {"targetSystem": service["targetSystem"], "operation": service["operation"],
                                                               "value": ref["value"], "unit": service["unit"]}})
        quote_items.append({"id": str(index), "action": "add", "productOffering": {"id": oid, "name": offer["name"]},
                            "product": {"productCharacteristic": characteristics},
                            "pricingDecision": {"baseMonthlyPrice": base_monthly, "discountPercent": money(decision["discountPercent"])},
                            "itemPrice": [{"priceType": "recurring", "price": _amount(monthly_price)},
                                          {"priceType": "oneTime", "price": _amount(setup_price)}]})
    request_id, stamp = request["requestId"], decision_time.isoformat()
    quote = {"id": f"quote-{request_id}", "@type": "Quote", "state": "pending" if approval else "approved",
             "externalId": request_id, "quoteDate": stamp, "relatedParty": [{"id": request["customerId"], "role": "customer"}],
             "quoteItem": quote_items,
             "quoteTotalPrice": [{"priceType": "recurring", "price": _amount(monthly)}, {"priceType": "oneTime", "price": _amount(setup)}],
             "note": [{"text": "Illustrative pre-tax catalogue price; no network provisioning has occurred."}]}
    order = None if approval else {"id": f"order-{request_id}", "@type": "ProductOrder", "state": "acknowledged",
                                   "externalId": request_id, "orderDate": stamp, "quote": [{"id": quote["id"]}],
                                   "productOrderItem": [{"id": i["id"], "action": "add", "productOffering": i["productOffering"],
                                                         "product": i["product"]} for i in quote_items]}
    service_order = None if approval else {"id": f"service-order-{request_id}", "@type": "ServiceOrder",
                                           "state": "acknowledged", "externalId": request_id, "productOrder": {"id": order["id"]},
                                           "orderItem": service_items}
    proposal_snapshot = {"productOfferingIds": ids, "discountPercent": money(discount),
                         "exceptionRequested": proposal.get("exceptionRequested", False), "reason": str(proposal.get("reason", ""))}
    rule_trace = [{"productOfferingId": oid, **row} for oid in ids for row in decisions[oid]["trace"]]
    return {"requestId": request_id, "catalogueVersion": catalogue["version"], "catalogueSnapshot": catalogue,
            "cpqPolicyVersion": policy["version"], "cpqPolicySnapshot": policy,
            "rulesVersion": rules["version"], "rulesDigest": digest(rules), "ruleSnapshot": rules,
            "proposalSnapshot": proposal_snapshot, "ruleDecisions": rule_trace,
            "status": "PENDING_APPROVAL" if approval else "VALIDATED",
            "approval": {"required": approval, "proposedDiscountPercent": money(max(d["discountPercent"] for d in decisions.values())), "reason": str(proposal.get("reason", ""))},
            "request": request, "quote": quote, "productOrder": order, "serviceOrder": service_order}


def approve_result(result, approver, decision):
    if result.get("status") != "PENDING_APPROVAL" or not approver.strip() or decision not in ("approve", "reject"):
        raise ValidationError("pending result and an explicit approver decision required")
    updated = copy.deepcopy(result)
    updated["approval"].update({"decision": decision, "approver": approver, "decidedAt": datetime.now(timezone.utc).isoformat()})
    if decision == "reject":
        updated["status"], updated["quote"]["state"] = "REJECTED", "rejected"
        return updated
    if any(key not in updated for key in ("ruleSnapshot", "proposalSnapshot", "cpqPolicySnapshot")):
        raise ValidationError("Approval needs the original rule, product policy and proposal snapshots")
    base = build_result(updated["request"], updated["proposalSnapshot"], updated["catalogueSnapshot"],
                        updated["ruleSnapshot"], policy=updated["cpqPolicySnapshot"],
                        as_of=datetime.fromisoformat(updated["quote"]["quoteDate"]),
                        _approval_granted=True)
    base["approval"], base["status"] = updated["approval"], "APPROVED"
    base["approval"]["required"] = False
    return base
