"""Product combination rules shared by CPQ and the agent order path."""


class ProductConstraintError(ValueError):
    pass


def evaluate_constraints(selected, policy):
    selected = set(selected)
    checks = []
    for constraint in policy["productConstraints"]:
        if constraint["kind"] == "excludes":
            passed = not all(oid in selected for oid in constraint["offeringIds"])
        else:
            passed = constraint["offeringId"] not in selected or any(
                oid in selected for oid in constraint["requiredOfferingIds"])
        checks.append({"id": constraint["id"], "passed": passed, "reason": constraint["reason"]})
        if not passed:
            raise ProductConstraintError(f"Product combination invalid: {constraint['reason']}")
    return checks
