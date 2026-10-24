"""Small, data-driven decision tables. No eval, scripts, SQL or model-generated code."""
import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

RULES_PATH = Path(__file__).with_name("business_rules.json")
KINDS = {"eligibility", "price", "discount", "approval"}
TYPES = {"string", "number", "boolean", "list"}
OPERATORS = {"eq", "ne", "in", "notIn", "gt", "gte", "lt", "lte", "exists"}
_MISSING = object()


class RuleError(ValueError):
    pass


def number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise RuleError("Expected a finite number")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise RuleError("Expected a finite number") from exc
    if not result.is_finite():
        raise RuleError("Expected a finite number")
    return result


def instant(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError) as exc:
        raise RuleError("Effective dates must be ISO dates or timezone-aware timestamps") from exc
    if result.tzinfo is None:
        if len(value) != 10:
            raise RuleError("Effective timestamps need a timezone; date-only boundaries use UTC")
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def typed(value, kind):
    if kind == "number":
        return number(value)
    if kind == "string" and isinstance(value, str) and len(value) <= 1000:
        return value
    if kind == "boolean" and isinstance(value, bool):
        return value
    if kind == "list" and isinstance(value, list) and len(value) <= 1000 and all(
        isinstance(x, (str, int, float, bool)) and (not isinstance(x, float) or number(x).is_finite()) for x in value
    ):
        return value
    raise RuleError(f"Expected {kind} value")


def only_keys(obj, allowed, subject):
    if not isinstance(obj, dict) or set(obj) - set(allowed):
        raise RuleError(f"Invalid fields in {subject}")


def outcome_check(outcome, kind, columns):
    fields = {"eligibility": {"eligible"}, "price": {"monthlyPrice", "setupPrice"},
              "discount": {"discountPercent"}, "approval": {"decision"}}[kind]
    if not isinstance(outcome, dict) or set(outcome) != fields:
        raise RuleError(f"{kind} outcome needs {', '.join(sorted(fields))}")
    if kind == "eligibility" and not isinstance(outcome["eligible"], bool):
        raise RuleError("Eligibility outcome must be true or false")
    if kind == "approval" and outcome["decision"] not in ("approve", "review", "reject"):
        raise RuleError("Approval outcome must be approve, review or reject")
    if kind not in ("price", "discount"):
        return
    for value in outcome.values():
        if isinstance(value, dict):
            if (set(value) != {"column"} or not isinstance(value["column"], str)
                    or value["column"] not in columns or columns[value["column"]]["type"] != "number"):
                raise RuleError("A numeric output reference must name a numeric column")
        else:
            amount = number(value)
            maximum = 100 if kind == "discount" else 1000000
            if amount < 0 or amount > maximum or amount.as_tuple().exponent < -2:
                raise RuleError(f"{kind} output is outside its range or has more than two decimals")


def validate_rules(rules):
    only_keys(rules, {"version", "columns", "tables"}, "rule configuration")
    if not isinstance(rules.get("version"), str) or not rules["version"]:
        raise RuleError("Rules need a version")
    if not isinstance(rules.get("columns"), list) or not 1 <= len(rules["columns"]) <= 100:
        raise RuleError("Rules need 1 to 100 column definitions")
    columns = {}
    for column in rules["columns"]:
        only_keys(column, {"id", "label", "type", "source", "default"}, "column")
        cid, source = column.get("id"), column.get("source")
        if not isinstance(cid, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", cid) or cid in columns:
            raise RuleError("Column IDs must be unique simple identifiers")
        if not isinstance(column.get("type"), str) or column["type"] not in TYPES or not isinstance(column.get("label"), str) or not column["label"]:
            raise RuleError(f"{cid} needs a label and supported type")
        if not isinstance(source, str) or not re.fullmatch(
            r"(?:request\.(?:segment|customerId)|request\.context\.[A-Za-z][A-Za-z0-9_]*|"
            r"offer\.[A-Za-z][A-Za-z0-9_]*|proposal\.(?:discountPercent|exceptionRequested)|derived\.discountPercent)", source
        ):
            raise RuleError(f"Unsupported data source for {cid}")
        if "default" in column:
            typed(column["default"], column["type"])
        columns[cid] = column
    tables = rules.get("tables")
    if not isinstance(tables, list) or len(tables) != 4:
        raise RuleError("Exactly one table for each of eligibility, price, discount and approval is required")
    kinds, table_ids = set(), set()
    for table in tables:
        only_keys(table, {"id", "name", "kind", "defaultOutcome", "rows"}, "table")
        kind = table.get("kind")
        if not isinstance(kind, str) or kind not in KINDS or kind in kinds or not isinstance(table.get("id"), str) or not table["id"] or table["id"] in table_ids:
            raise RuleError("Table IDs and kinds must be unique")
        kinds.add(kind)
        table_ids.add(table["id"])
        if not isinstance(table.get("name"), str) or not table["name"]:
            raise RuleError("Table needs a name")
        outcome_check(table.get("defaultOutcome"), kind, columns)
        if not isinstance(table.get("rows"), list) or len(table["rows"]) > 500:
            raise RuleError("Each table accepts at most 500 rows")
        row_ids = set()
        for row in table["rows"]:
            only_keys(row, {"id", "enabled", "priority", "conditions", "outcome", "reason", "effectiveFrom", "effectiveTo"}, "row")
            rid = row.get("id")
            if not isinstance(rid, str) or not rid or len(rid) > 100 or rid in row_ids:
                raise RuleError("Row IDs must be unique within a table")
            row_ids.add(rid)
            if not isinstance(row.get("enabled"), bool) or type(row.get("priority")) is not int or not 0 <= row["priority"] <= 1000000:
                raise RuleError(f"{rid} needs enabled and a nonnegative integer priority")
            if not isinstance(row.get("reason"), str) or not 1 <= len(row["reason"]) <= 1000:
                raise RuleError(f"{rid} needs a short explanation")
            for key in ("effectiveFrom", "effectiveTo"):
                if key in row and (not isinstance(row[key], str) or not row[key]):
                    raise RuleError("Effective boundaries must be nonempty date strings")
            start = instant(row["effectiveFrom"]) if row.get("effectiveFrom") else None
            end = instant(row["effectiveTo"]) if row.get("effectiveTo") else None
            if start and end and start >= end:
                raise RuleError(f"{rid} effective end must follow its start")
            conditions = row.get("conditions")
            if not isinstance(conditions, list) or len(conditions) > 20:
                raise RuleError(f"{rid} accepts at most 20 conditions")
            for condition in conditions:
                only_keys(condition, {"column", "operator", "value", "valueFrom"}, "condition")
                cid, op = condition.get("column"), condition.get("operator")
                if not isinstance(cid, str) or not isinstance(op, str) or cid not in columns or op not in OPERATORS:
                    raise RuleError(f"Unknown column or operator in {rid}")
                if kind != "approval" and columns[cid]["source"].startswith("derived."):
                    raise RuleError("Effective discount can only be used in the approval table")
                if ("value" in condition) == ("valueFrom" in condition):
                    raise RuleError("Condition needs exactly one literal value or valueFrom column")
                right_type = "boolean" if op == "exists" else "list" if op in ("in", "notIn") else columns[cid]["type"]
                if op in ("gt", "gte", "lt", "lte") and columns[cid]["type"] != "number":
                    raise RuleError("Ordered comparisons need a numeric column")
                if "valueFrom" in condition:
                    if not isinstance(condition["valueFrom"], str):
                        raise RuleError("Comparison column must be a column ID")
                    rhs = columns.get(condition["valueFrom"])
                    if rhs is None or rhs["type"] != right_type or (kind != "approval" and rhs["source"].startswith("derived.")):
                        raise RuleError("Comparison column has an incompatible type or phase")
                else:
                    typed(condition["value"], right_type)
            outcome_check(row.get("outcome"), kind, columns)
        # Output references must be available at that table's phase too.
        for outcome in [table["defaultOutcome"]] + [r["outcome"] for r in table["rows"]]:
            for value in outcome.values():
                if isinstance(value, dict) and columns[value["column"]]["source"].startswith("derived."):
                    raise RuleError("A calculated discount cannot feed back into pricing or discounts")
    return rules


def load_rules(path=None):
    try:
        return validate_rules(json.loads(Path(path or RULES_PATH).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuleError("Could not load business rule configuration") from exc


def digest(rules):
    return hashlib.sha256(json.dumps(rules, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _values(rules, context):
    values = {}
    for column in rules["columns"]:
        value = context
        for part in column["source"].split("."):
            value = value.get(part, _MISSING) if isinstance(value, dict) else _MISSING
        if value is _MISSING and "default" in column:
            value = column["default"]
        values[column["id"]] = _MISSING if value is _MISSING else typed(value, column["type"])
    return values


def _match(row, values):
    unknown, checks = [], []
    for condition in row["conditions"]:
        cid, op = condition["column"], condition["operator"]
        left = values[cid]
        right = values[condition["valueFrom"]] if "valueFrom" in condition else condition["value"]
        if op == "exists" and right is not _MISSING:
            checks.append((left is not _MISSING) == right)
        elif left is _MISSING or right is _MISSING:
            unknown.append(cid if left is _MISSING else condition["valueFrom"])
        else:
            if isinstance(left, Decimal) and op not in ("in", "notIn"):
                right = number(right)
            if op in ("in", "notIn") and isinstance(left, Decimal):
                right = [number(x) for x in right]
            checks.append({"eq": lambda: left == right, "ne": lambda: left != right,
                           "in": lambda: left in right, "notIn": lambda: left not in right,
                           "gt": lambda: left > right, "gte": lambda: left >= right,
                           "lt": lambda: left < right, "lte": lambda: left <= right}[op]())
    # A false AND operand disproves the row even when another operand is missing.
    return False if False in checks else None if unknown else True, unknown


def evaluate_table(table, values, when):
    rows = [r for r in table["rows"] if r["enabled"]
            and (not r.get("effectiveFrom") or instant(r["effectiveFrom"]) <= when)
            and (not r.get("effectiveTo") or when < instant(r["effectiveTo"]))]
    selected = None
    for priority in sorted({r["priority"] for r in rows}, reverse=True):
        matches, missing = [], set()
        for row in (r for r in rows if r["priority"] == priority):
            matched, unknown = _match(row, values)
            if matched is None:
                missing.update(unknown)
            elif matched:
                matches.append(row)
        if missing:
            raise RuleError(f"{table['name']} needs information: {', '.join(sorted(missing))}")
        if len(matches) > 1:
            raise RuleError(f"Conflicting rows at priority {priority} in {table['name']}")
        if matches:
            selected = matches[0]
            break
    result = copy.deepcopy(selected["outcome"] if selected else table["defaultOutcome"])
    for key, value in result.items():
        if isinstance(value, dict):
            value = values[value["column"]]
            if value is _MISSING:
                raise RuleError(f"Missing output data for {table['name']}")
            result[key] = value
    return result, {"tableId": table["id"], "kind": table["kind"], "rowId": selected["id"] if selected else "default",
                    "reason": selected["reason"] if selected else "Table fallback applied."}


def evaluate_offer(rules, request, proposal, offer, when):
    """Rules are validated by the caller once; only allowlisted proposal fields enter context."""
    context = {"request": request, "offer": offer,
               "proposal": {"discountPercent": proposal.get("discountPercent", 0),
                            "exceptionRequested": proposal.get("exceptionRequested", False)}, "derived": {}}
    trace, outcomes = [], {}
    tables = {t["kind"]: t for t in rules["tables"]}
    for kind in ("eligibility", "price", "discount", "approval"):
        outcome, matched = evaluate_table(tables[kind], _values(rules, context), when)
        trace.append(matched)
        outcomes[kind] = outcome
        if kind == "eligibility" and not outcome["eligible"]:
            raise RuleError(f"{offer['id']} is ineligible: {matched['reason']}")
        if kind == "discount":
            configured = number(outcome["discountPercent"])
            requested = number(proposal.get("discountPercent", 0))
            if not 0 <= configured <= 100:
                raise RuleError("Configured discount is outside 0 to 100")
            context["derived"]["discountPercent"] = max(configured, requested)
        if kind == "approval" and outcome["decision"] == "reject":
            raise RuleError(f"Quote rejected by policy: {matched['reason']}")
    return {"monthlyPrice": outcomes["price"]["monthlyPrice"], "setupPrice": outcomes["price"]["setupPrice"],
            "discountPercent": context["derived"]["discountPercent"],
            "requiresApproval": outcomes["approval"]["decision"] == "review", "trace": trace}
