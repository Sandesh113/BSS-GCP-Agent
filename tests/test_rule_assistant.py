"""Spoken or typed rules: Gemini proposes one row, the rules engine validates, a person saves."""

import copy

import pytest

from business_rules import RuleError, load_rules
from rule_assistant import apply_change
from ui import app as ui

CONTRACT_COLUMN = {"id": "contractMonths", "label": "Contract months", "type": "number", "inputKey": "contractMonths"}
PRICE_ROW = {"id": "Mini 24 month price", "priority": 150,
             "conditions": [{"column": "offerId", "operator": "eq", "value": "po-mobile-mini"},
                            {"column": "contractMonths", "operator": "eq", "value": 24}],
             "outcome": {"monthlyPrice": "15.00", "setupPrice": {"column": "baseSetupPrice"}},
             "reason": "Mobile Mini is £15 a month on a 24-month contract."}
CHANGE = {"table": "price", "newColumns": [CONTRACT_COLUMN], "row": PRICE_ROW, "summary": "24-month Mobile Mini price"}


def propose(client, change, version=None, message="Mobile Mini costs £15 a month on a 24-month contract", monkeypatch=None):
    monkeypatch.setattr(ui, "propose_rule_change", lambda *args: copy.deepcopy(change))
    version = version or client.get("/api/rules").json["version"]
    return client.post("/api/rules/assistant/propose", json={"message": message, "version": version})


def test_spoken_rule_is_drafted_validated_and_only_applies_after_save(monkeypatch):
    client = ui.app.test_client()
    before = client.get("/api/rules").json
    response = propose(client, CHANGE, monkeypatch=monkeypatch)
    assert response.status_code == 200, response.json
    preview = response.json["preview"]
    assert preview["table"] == "price" and preview["row"]["id"] == "mini-24-month-price"
    assert preview["newColumns"][0]["source"] == "request.context.contractMonths"
    assert client.get("/api/rules").json == before  # drafting saves nothing

    saved = client.put("/api/rules", json=response.json["candidate"])
    assert saved.status_code == 200, saved.json
    quote = lambda months: client.post("/api/preview", json={"customerId": "c", "segment": "consumer", "text": "Mini",
                                                            "productOfferingId": "po-mobile-mini",
                                                            "context": {"contractMonths": months}}).json
    assert quote(24)["quote"]["quoteTotalPrice"][0]["price"]["dutyFreeAmount"]["value"] == "15.00"
    assert quote(12)["quote"]["quoteTotalPrice"][0]["price"]["dutyFreeAmount"]["value"] == "12.00"


def test_stale_editor_and_clarification(monkeypatch):
    client = ui.app.test_client()
    assert propose(client, CHANGE, version="stale", monkeypatch=monkeypatch).status_code == 409
    asked = propose(client, {"clarification": "Which offering should the price apply to?"}, monkeypatch=monkeypatch)
    assert asked.status_code == 200 and asked.json["preview"]["clarification"].startswith("Which offering")
    assert asked.json["candidate"] is None


@pytest.mark.parametrize("damage", [
    lambda c: c.update(table="pricing"),
    lambda c: c["row"]["conditions"][0].update(operator="eval"),
    lambda c: c["row"]["conditions"].append({"column": "discountPercent", "operator": "gt", "value": 0}),
    lambda c: c["newColumns"][0].update(inputKey="__import__('os')"),
    lambda c: c["newColumns"].append({"id": "segment", "label": "Segment", "type": "number", "inputKey": "segment"}),
    lambda c: c["row"].update(enabled=False, delete=["eligible-segment"]),
    lambda c: c["row"].update(outcome={"monthlyPrice": "-5.00", "setupPrice": "0.00"}),
    lambda c: c["row"].update(effectiveFrom="2028-01-01", effectiveTo="2027-01-01"),
    lambda c: c.update(newColumns=[dict(CONTRACT_COLUMN, id=f"c{i}", inputKey=f"c{i}") for i in range(4)]),
])
def test_invalid_model_proposals_are_rejected_without_saving(damage, monkeypatch):
    client = ui.app.test_client()
    before = client.get("/api/rules").json
    change = copy.deepcopy(CHANGE)
    damage(change)
    response = propose(client, change, monkeypatch=monkeypatch)
    assert response.status_code == 400 and "not valid" in response.json["error"]
    assert client.get("/api/rules").json == before


def test_assistant_only_adds_and_never_mutates_existing_rules():
    rules = load_rules()
    original = copy.deepcopy(rules)
    first, _ = apply_change(rules, CHANGE)
    assert rules == original
    again, preview = apply_change(first, {**CHANGE, "newColumns": [CONTRACT_COLUMN]})
    assert preview["row"]["id"] == "mini-24-month-price-2" and preview["newColumns"] == []
    assert "Same priority as mini-24-month-price" in preview["warnings"][0]
    for table_before, table_after in zip(original["tables"], again["tables"]):
        assert table_after["rows"][:len(table_before["rows"])] == table_before["rows"]


def test_string_priority_is_read_but_other_text_is_rejected():
    _, preview = apply_change(load_rules(), {**CHANGE, "row": {**PRICE_ROW, "priority": "120"}})
    assert preview["row"]["priority"] == 120
    with pytest.raises(RuleError):
        apply_change(load_rules(), {**CHANGE, "row": {**PRICE_ROW, "priority": "high"}})


@pytest.mark.parametrize("input_key", ["request.contractMonths", "request.context.contractMonths", "context.contractMonths"])
def test_model_input_path_is_normalised_to_customer_context(input_key):
    change = {**CHANGE, "newColumns": [dict(CONTRACT_COLUMN, inputKey=input_key)]}
    candidate, preview = apply_change(load_rules(), change)
    assert preview["newColumns"][0]["source"] == "request.context.contractMonths"
    assert candidate["columns"][-1]["source"] == "request.context.contractMonths"


def test_model_failure_is_a_502_and_voice_script_is_served(monkeypatch):
    client = ui.app.test_client()
    monkeypatch.setattr(ui, "propose_rule_change", lambda *args: (_ for _ in ()).throw(RuntimeError("model down")))
    version = client.get("/api/rules").json["version"]
    failed = client.post("/api/rules/assistant/propose", json={"message": "Business customers get 5% off", "version": version})
    assert failed.status_code == 502
    assert client.post("/api/rules/assistant/propose", json={"message": " ", "version": version}).status_code == 400
    assert client.get("/voice.js").status_code == 200
