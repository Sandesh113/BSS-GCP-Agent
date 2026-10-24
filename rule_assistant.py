"""Natural-language authoring of decision-table rows. Gemini proposes; business_rules validates."""

from __future__ import annotations

import copy
import json
import os
import re

from business_rules import KINDS, OPERATORS, RuleError, validate_rules

OUTCOME_SHAPES = {
    "eligibility": '{"eligible": true|false}',
    "price": '{"monthlyPrice": "15.00", "setupPrice": "0.00"}; use {"column": "baseMonthlyPrice"} or '
             '{"column": "baseSetupPrice"} for a price the rule does not change',
    "discount": '{"discountPercent": "10.00"}',
    "approval": '{"decision": "approve"|"review"|"reject"}',
}
ROW_KEYS = {"id", "priority", "conditions", "outcome", "reason", "effectiveFrom", "effectiveTo"}
COLUMN_KEYS = {"id", "label", "type", "inputKey", "default"}
MAX_NEW_COLUMNS = 3


def rule_context(rules, offerings):
    """What the model may refer to. It sees column and row IDs, never the evaluator."""
    return {"columns": [{k: c[k] for k in ("id", "label", "type", "source")} for c in rules["columns"]],
            "tables": [{"kind": t["kind"], "name": t["name"],
                        "rows": [{"id": r["id"], "priority": r["priority"]} for r in t["rows"]]} for t in rules["tables"]],
            "operators": sorted(OPERATORS), "outcomeShapes": OUTCOME_SHAPES,
            "offerings": [{"id": o["id"], "name": o["name"]} for o in offerings]}


def propose_change(message, rules, offerings):
    """Ask Gemini for one proposed row; the result is untrusted until apply_change validates it."""
    import google.auth
    from google.auth.transport.requests import Request
    import requests

    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT_ID")
    if not project:
        raise RuntimeError("Rule assistant model is not configured")
    region = os.environ.get("MODEL_REGION", "eu")
    model = os.environ.get("MODEL_NAME", "gemini-3.5-flash")
    endpoint = os.environ.get("MODEL_API_ENDPOINT", "https://aiplatform.eu.rep.googleapis.com").rstrip("/")
    instruction = (
        "Turn the business user's rule into ONE new decision-table row. Return one JSON object: "
        '{"table": eligibility|price|discount|approval, "newColumns": [{"id", "label", "type": string|number|boolean|list, '
        '"inputKey", "default"?}], "row": {"id", "priority": integer, "conditions": [{"column", "operator", "value"}], '
        '"outcome": {...}, "reason", "effectiveFrom"?: "YYYY-MM-DD", "effectiveTo"?: "YYYY-MM-DD"}, "summary": short sentence}. '
        "Use existing column IDs where they fit; add a newColumn only for a customer input that does not exist yet. "
        "For a newColumn, inputKey is only the bare key, such as contractMonths, without request or context prefixes. "
        "Refer to offerings by their ID. Money and percentages are strings with at most two decimals. "
        "effectiveTo is exclusive. Use the outcome shape for the chosen table. Never edit or delete existing rows. "
        'If the rule is ambiguous or missing a value, return {"clarification": "one short question"} instead. JSON only.'
    )
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(Request())
    payload = {"systemInstruction": {"parts": [{"text": instruction}]},
               "contents": [{"role": "user", "parts": [{"text": json.dumps({
                   "rule": message, "configuration": rule_context(rules, offerings)})}]}],
               "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
    url = f"{endpoint}/v1/projects/{project}/locations/{region}/publishers/google/models/{model}:generateContent"
    response = requests.post(url, headers={"Authorization": f"Bearer {credentials.token}",
                                           "Content-Type": "application/json"}, json=payload, timeout=60)
    response.raise_for_status()
    parts = response.json()["candidates"][0]["content"]["parts"]
    proposal = json.loads("".join(part.get("text", "") for part in parts))
    if not isinstance(proposal, dict):
        raise ValueError("Model returned an invalid rule proposal")
    return proposal


def _slug(value, fallback):
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")[:60]
    return slug or fallback


def _input_key(value):
    """Accept the model's common path spellings, then pin all new inputs to request.context."""
    key = value
    if not isinstance(key, str):
        return key
    for prefix in ("request.context.", "request.", "context."):
        if key.startswith(prefix):
            key = key[len(prefix):]
            break
    return key


def apply_change(rules, change):
    """Add the proposed columns and row to a copy of the rules; nothing existing can change.

    Returns (candidate, preview) for review, or (None, {"clarification": question})."""
    if not isinstance(change, dict):
        raise RuleError("Could not read that rule")
    if isinstance(change.get("clarification"), str) and change["clarification"].strip():
        return None, {"clarification": change["clarification"].strip()[:300]}
    kind = change.get("table")
    if kind not in KINDS:
        raise RuleError("The rule must belong to the eligibility, price, discount or approval table")
    candidate = copy.deepcopy(rules)
    existing = {c["id"]: c for c in candidate["columns"]}
    new_columns = change.get("newColumns") or []
    if not isinstance(new_columns, list) or len(new_columns) > MAX_NEW_COLUMNS:
        raise RuleError(f"A rule can add at most {MAX_NEW_COLUMNS} input columns")
    added = []
    for raw in new_columns:
        if not isinstance(raw, dict) or set(raw) - COLUMN_KEYS:
            raise RuleError("Invalid fields in a proposed input column")
        # New columns are always customer inputs; offer fields and calculated values stay built-in.
        input_key = _input_key(raw.get("inputKey") or raw.get("id"))
        column = {"id": raw.get("id"), "label": raw.get("label"), "type": raw.get("type"),
                  "source": f"request.context.{input_key}"}
        if "default" in raw and raw["default"] is not None:
            column["default"] = raw["default"]
        if column["id"] in existing:
            if {k: existing[column["id"]].get(k) for k in ("type", "source")} != {k: column[k] for k in ("type", "source")}:
                raise RuleError(f"Column {column['id']} already exists with a different meaning")
            continue
        candidate["columns"].append(column)
        existing[column["id"]] = column
        added.append(column)
    raw_row = change.get("row")
    if not isinstance(raw_row, dict) or set(raw_row) - ROW_KEYS:
        raise RuleError("Invalid fields in the proposed row")
    table = next(t for t in candidate["tables"] if t["kind"] == kind)
    row_id, taken, n = _slug(raw_row.get("id"), "assistant-rule"), {r["id"] for r in table["rows"]}, 2
    base = row_id
    while row_id in taken:
        row_id, n = f"{base}-{n}", n + 1
    priority = raw_row.get("priority", 100)
    if isinstance(priority, str) and priority.strip().isdigit():
        priority = int(priority)
    row = {"id": row_id, "enabled": True,
           "priority": priority, "conditions": raw_row.get("conditions", []),
           "outcome": raw_row.get("outcome"), "reason": str(raw_row.get("reason") or change.get("summary") or "")[:1000]}
    for key in ("effectiveFrom", "effectiveTo"):
        if raw_row.get(key):
            row[key] = raw_row[key]
    table["rows"].append(row)
    validate_rules(candidate)
    clashes = [r["id"] for r in table["rows"] if r is not row and r["enabled"] and r["priority"] == row["priority"]]
    warnings = [f"Same priority as {', '.join(clashes)}: if both match one quote, the quote is blocked as a conflict."] if clashes else []
    return candidate, {"table": kind, "tableName": table["name"], "row": row, "newColumns": added,
                       "summary": str(change.get("summary") or "")[:300], "warnings": warnings}
