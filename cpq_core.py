"""Deterministic local CPQ: catalogue offers, customer, terms, constraints and promotions."""
import copy
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from business_rules import RuleError, evaluate_offer, instant, load_rules, number, validate_rules
from catalogue_core import DEFAULT_CATALOGUE, ValidationError, money, validate_catalogue
from customer_core import validate_customer
from product_constraints import ProductConstraintError, evaluate_constraints

POLICY_PATH = Path(__file__).with_name("cpq_policy.json")


def _ids(values, subject):
    if not isinstance(values, list) or not values or len(values) > 20 or any(not isinstance(v, str) or not v for v in values) or len(values) != len(set(values)):
        raise ValidationError(f"{subject} needs unique offering IDs")
    return values


def validate_policy(policy):
    if not isinstance(policy, dict) or policy.get("currency") != "GBP" or not isinstance(policy.get("version"), str):
        raise ValidationError("CPQ policy needs a version and GBP currency")
    for key in ("termPrices", "productConstraints", "promotions"):
        if not isinstance(policy.get(key), list) or len(policy[key]) > 500:
            raise ValidationError(f"CPQ {key} must be a list of at most 500")
    terms = set()
    for row in policy["termPrices"]:
        if not isinstance(row, dict) or not isinstance(row.get("offeringId"), str) or type(row.get("months")) is not int or not 1 <= row["months"] <= 60:
            raise ValidationError("Term price needs an offering and 1–60 months")
        key = (row["offeringId"], row["months"])
        if key in terms:
            raise ValidationError("Term price rows must be unique")
        terms.add(key)
        try:
            price = number(row.get("monthlyPrice"))
        except RuleError as exc:
            raise ValidationError("Term price must be a numeric GBP amount") from exc
        if price < 0 or price > 1000000 or price.as_tuple().exponent < -2:
            raise ValidationError("Term price must be a GBP amount with two decimals")
    ids = set()
    for row in policy["productConstraints"]:
        if not isinstance(row, dict) or row.get("kind") not in ("excludes", "requiresAny") or not isinstance(row.get("id"), str) or not row["id"] or row["id"] in ids or not isinstance(row.get("reason"), str) or not row["reason"]:
            raise ValidationError("Product constraint needs a unique ID, kind and reason")
        ids.add(row["id"])
        if row["kind"] == "excludes":
            if len(_ids(row.get("offeringIds"), "Exclusion")) != 2:
                raise ValidationError("Exclusion needs exactly two offerings")
        elif not isinstance(row.get("offeringId"), str) or not row["offeringId"] or row["offeringId"] in _ids(row.get("requiredOfferingIds"), "Requirement"):
            raise ValidationError("Requirement needs an add-on and different parent offers")
    ids = set()
    for row in policy["promotions"]:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] or row["id"] in ids or not isinstance(row.get("name"), str) or not row["name"]:
            raise ValidationError("Promotion needs a unique ID and name")
        ids.add(row["id"])
        _ids(row.get("offeringIds"), "Promotion")
        try:
            start, end = instant(row.get("validFrom")), instant(row.get("validTo"))
            percent = number(row.get("discountPercent"))
        except RuleError as exc:
            raise ValidationError(str(exc)) from exc
        if start >= end or not 0 <= percent <= 100 or percent.as_tuple().exponent < -2:
            raise ValidationError("Promotion needs a valid window and 0–100% discount")
    return policy


def load_policy(path=None):
    try:
        return validate_policy(json.loads(Path(path or POLICY_PATH).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError("Could not load CPQ policy") from exc


def available_terms(policy, offering_id):
    terms = sorted(row["months"] for row in policy["termPrices"] if row["offeringId"] == offering_id)
    return terms or [12]


def _amount(amount):
    return {"dutyFreeAmount": {"value": money(amount), "unit": "GBP"}}


def configure_quote(customer, selections, promotion_id=None, *, catalogue=None, rules=None, policy=None, as_of=None):
    customer = validate_customer(customer)
    catalogue = validate_catalogue(copy.deepcopy(catalogue if catalogue is not None else DEFAULT_CATALOGUE), allow_drafts=True)
    rules = copy.deepcopy(load_rules() if rules is None else validate_rules(rules))
    policy = validate_policy(copy.deepcopy(policy if policy is not None else load_policy()))
    when = as_of or datetime.now(timezone.utc)
    if not isinstance(when, datetime) or when.tzinfo is None:
        raise ValidationError("Quote time needs a timezone")
    if not isinstance(selections, list) or not 1 <= len(selections) <= 10:
        raise ValidationError("Select 1 to 10 products")
    offers = {offer["id"]: offer for offer in catalogue["productOfferings"]}
    specs = {spec["id"]: spec for spec in catalogue["productSpecifications"]}
    selected = []
    for line in selections:
        if not isinstance(line, dict) or not isinstance(line.get("offeringId"), str) or type(line.get("termMonths")) is not int:
            raise ValidationError("Each product needs an offering and term")
        oid, months = line["offeringId"], line["termMonths"]
        if oid in selected:
            raise ValidationError("This preview accepts one of each offering per quote")
        if oid not in offers or offers[oid]["lifecycleStatus"] != "Active":
            raise ValidationError(f"{oid} is not an Active offering")
        if months not in available_terms(policy, oid):
            raise ValidationError(f"{oid} does not offer a {months}-month term")
        selected.append(oid)
    try:
        checks = evaluate_constraints(selected, policy)
    except ProductConstraintError as exc:
        raise ValidationError(str(exc)) from exc
    promotion = None
    if promotion_id:
        promotion = next((p for p in policy["promotions"] if p["id"] == promotion_id), None)
        if promotion is None:
            raise ValidationError("Unknown promotion")
        if not instant(promotion["validFrom"]) <= when < instant(promotion["validTo"]):
            raise ValidationError(f"{promotion['name']} is not active at quote time")
        if not any(oid in promotion["offeringIds"] for oid in selected):
            raise ValidationError(f"{promotion['name']} does not apply to selected products")
    quote_items, rule_decisions = [], []
    monthly_total = setup_total = commitment_total = Decimal(0)
    approval = False
    for index, line in enumerate(selections, 1):
        oid, months = line["offeringId"], line["termMonths"]
        offer = copy.deepcopy(offers[oid])
        term_price = next((r["monthlyPrice"] for r in policy["termPrices"] if r["offeringId"] == oid and r["months"] == months), offer["monthlyPrice"])
        offer["monthlyPrice"] = term_price
        promo_percent = promotion["discountPercent"] if promotion and oid in promotion["offeringIds"] else "0.00"
        request = {"requestId": "cpq-evaluation", "customerId": customer["id"], "segment": customer["segment"], "text": "CPQ configuration",
                   "context": {"termMonths": months, "channel": "cpq"}}
        try:
            decision = evaluate_offer(rules, request, {"discountPercent": promo_percent, "exceptionRequested": False}, offer, when)
        except RuleError as exc:
            raise ValidationError(str(exc)) from exc
        approval = approval or decision["requiresApproval"]
        base = Decimal(money(decision["monthlyPrice"]))
        setup = Decimal(money(decision["setupPrice"]))
        recurring = Decimal(money(base * (Decimal(100) - decision["discountPercent"]) / Decimal(100)))
        monthly_total += recurring
        setup_total += setup
        commitment_total += recurring * months + setup
        spec = specs[offer["productSpecification"]["id"]]
        characteristics = [{"name": specs[ref["id"]]["characteristic"], "value": ref["value"], "unit": specs[ref["id"]]["unit"],
                            "productSpecification": {"id": ref["id"], "name": specs[ref["id"]]["name"]}}
                           for ref in spec["bundledProductSpecification"]]
        quote_items.append({"id": str(index), "action": "add", "productOffering": {"id": oid, "name": offer["name"]},
                            "product": {"productCharacteristic": characteristics}, "termMonths": months,
                            "pricingDecision": {"catalogueMonthlyPrice": money(offers[oid]["monthlyPrice"]), "termMonthlyPrice": money(term_price),
                                                "baseMonthlyPrice": money(base), "discountPercent": money(decision["discountPercent"]),
                                                "promotionId": promotion["id"] if promo_percent != "0.00" else None},
                            "itemPrice": [{"priceType": "recurring", "price": _amount(recurring)}, {"priceType": "oneTime", "price": _amount(setup)}]})
        rule_decisions.extend({"productOfferingId": oid, **step} for step in decision["trace"])
    quote_id = "quote-" + uuid.uuid4().hex[:12]
    quote = {"id": quote_id, "@type": "Quote", "state": "pendingApproval" if approval else "draft", "quoteDate": when.isoformat(),
             "relatedParty": [{"id": customer["id"], "role": "customer"}], "quoteItem": quote_items,
             "quoteTotalPrice": [{"priceType": "recurring", "price": _amount(monthly_total)}, {"priceType": "oneTime", "price": _amount(setup_total)}],
             "note": [{"text": "Illustrative pre-tax quote. Commitment estimate assumes unchanged monthly charges for selected terms."}]}
    return {"status": "PENDING_APPROVAL" if approval else "VALIDATED", "quote": quote, "customerId": customer["id"],
            "catalogueVersion": catalogue["version"], "rulesVersion": rules["version"], "cpqPolicyVersion": policy["version"],
            "promotion": {"id": promotion["id"], "name": promotion["name"]} if promotion else None,
            "validation": checks, "ruleDecisions": rule_decisions, "commitmentEstimate": money(commitment_total),
            "approval": {"required": approval, "reason": "Discount requires human review" if approval else None}}
