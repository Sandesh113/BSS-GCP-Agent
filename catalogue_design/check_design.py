"""Check reference data integrity and price examples; this is not the rule engine."""
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def unique_ids(rows):
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate IDs")
    return set(ids)


def check():
    sources = read("sources.json")
    library = read("rule_library.json")
    blocks = read("building_blocks.json")
    examples = read("worked_examples.json")
    source_ids = unique_ids(sources["sources"])
    families = library["families"]
    family_ids = unique_ids(families)
    rules = [rule for family in families for rule in family["rules"]]
    rule_ids = unique_ids(rules)
    outcomes = set(library["ruleRecordContract"]["outcomes"])
    phases = unique_ids([{"id": row["stage"]} for row in blocks["decisionStages"]])
    for family in families:
        if not set(family["sourceIds"]) <= source_ids:
            raise ValueError(f"Unknown source in {family['id']}")
        if not set(family["phase"]) <= phases:
            raise ValueError(f"Unknown phase in {family['id']}")
        for rule in family["rules"]:
            if rule["failureOutcome"] not in outcomes or not rule["parameters"]:
                raise ValueError(f"Invalid rule {rule['id']}")
    services = blocks["serviceSpecifications"]
    products = blocks["productSpecifications"]
    service_ids = unique_ids(services)
    product_ids = unique_ids(products)
    if len(products) != 10 or len(services) != 7 or len(rules) != 72:
        raise ValueError("Reference model should contain 10 PS, 7 CFSS and 72 rules")
    for row in services + products + [blocks["compositeSpecification"]]:
        if not set(row["ruleIds"]) <= rule_ids:
            raise ValueError(f"Unknown rule binding for {row['id']}")
    for product in products:
        if product["realizes"]["serviceSpecificationId"] not in service_ids:
            raise ValueError(f"Unmapped product {product['id']}")
        selection = product["selection"]
        if selection["min"] < 0 or ("max" in selection and selection["max"] < selection["min"]):
            raise ValueError(f"Invalid selection cardinality {product['id']}")
    if set(blocks["compositeSpecification"]["childSpecificationIds"]) != product_ids:
        raise ValueError("Composite child references differ from the ten PS definitions")
    if blocks["offerTemplate"]["productSpecificationId"] != blocks["compositeSpecification"]["id"]:
        raise ValueError("Offer does not reference the root PS")
    if not set(blocks["offerTemplate"]["ruleFamilyIds"]) <= family_ids:
        raise ValueError("Unknown rule family")
    if set(blocks["sharedServicePolicy"]) != service_ids:
        raise ValueError("Missing CFS instance identity policy")

    # Verify mandatory CFS dependencies form an acyclic graph.
    graph = {row["id"]: row["requires"] for row in services}
    done = set()

    def visit(node, active):
        if node not in graph:
            raise ValueError(f"Unknown dependency {node}")
        if node in active:
            raise ValueError(f"Cyclic service dependency at {node}")
        if node in done:
            return
        for parent in graph[node]:
            visit(parent, active | {node})
        done.add(node)

    for node in graph:
        visit(node, set())

    price_ids = unique_ids(blocks["pricePolicyExamples"])
    prices = {row["id"]: row["pricePeriods"] for row in blocks["pricePolicyExamples"]}
    for policy_id, periods in prices.items():
        previous_end = None
        for period in periods:
            start, end = date.fromisoformat(period["startDate"]), date.fromisoformat(period["endDateExclusive"])
            try:
                amount = Decimal(period["amount"])
            except InvalidOperation as exc:
                raise ValueError(f"Invalid price in {policy_id}") from exc
            if start >= end or (previous_end is not None and start != previous_end):
                raise ValueError(f"Gap, overlap or unordered price in {policy_id}")
            if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
                raise ValueError(f"Invalid GBP amount in {policy_id}")
            previous_end = end

    unique_ids(examples["scenarios"])
    price_checks = 0
    for scenario in examples["scenarios"]:
        if not set(scenario["ruleIds"]) <= rule_ids:
            raise ValueError(f"Unknown example rule in {scenario['id']}")
        if scenario["kind"] == "priceLookup":
            if scenario["pricePolicyId"] not in price_ids:
                raise ValueError("Unknown price policy")
            when = date.fromisoformat(scenario["date"])
            matches = [p for p in prices[scenario["pricePolicyId"]]
                       if date.fromisoformat(p["startDate"]) <= when < date.fromisoformat(p["endDateExclusive"])]
            if len(matches) != 1 or matches[0]["amount"] != scenario["expectedAmount"]:
                raise ValueError(f"Price example failed: {scenario['id']}")
            price_checks += 1
        elif scenario["expectedOutcome"] not in outcomes:
            raise ValueError("Invalid expected outcome")
    print(f"Reference integrity OK: {len(families)} families, {len(rules)} rule templates, "
          f"{len(products)} PS, {len(services)} CFSS, {len(source_ids)} sources, "
          f"{len(examples['scenarios'])} design scenarios; {price_checks} price lookups verified.")
    print("Rule templates and non-price scenario outcomes are design definitions, not executed runtime rules.")


if __name__ == "__main__":
    check()
