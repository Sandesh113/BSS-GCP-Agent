import copy
import json
from datetime import datetime, timezone

import pytest

import business_rules
from business_rules import RuleError, load_rules, validate_rules
from catalogue_core import ValidationError, approve_result, build_result
from ui import app as ui

REQUEST = {"requestId":"rules-1", "customerId":"customer-1", "segment":"consumer", "text":"Mobile Mini"}
PROPOSAL = {"productOfferingIds":["po-mobile-mini"]}


def table(rules, kind):
    return next(t for t in rules["tables"] if t["kind"] == kind)


def row(rid, outcome, conditions=None, priority=100, **kwargs):
    return {"id":rid, "enabled":True, "priority":priority, "conditions":conditions or [],
            "outcome":outcome, "reason":"Configured table rule", **kwargs}


def test_editing_price_file_changes_next_quote_without_reload(tmp_path, monkeypatch):
    rules = load_rules()
    path = tmp_path / "rules.json"
    monkeypatch.setattr(business_rules, "RULES_PATH", path)
    path.write_text(json.dumps(rules), encoding="utf-8")
    assert build_result(REQUEST, PROPOSAL)["quote"]["quoteItem"][0]["pricingDecision"]["baseMonthlyPrice"] == "12.00"
    table(rules, "price")["rows"].append(row("new-price", {"monthlyPrice":"17.50", "setupPrice":"2.00"}))
    path.write_text(json.dumps(rules), encoding="utf-8")
    quoted = build_result(REQUEST, PROPOSAL)
    assert quoted["quote"]["quoteItem"][0]["pricingDecision"]["baseMonthlyPrice"] == "17.50"
    assert quoted["ruleDecisions"][1]["rowId"] == "new-price"


def test_new_column_and_threshold_drive_price_without_a_python_branch():
    rules = load_rules()
    rules["columns"].append({"id":"contractMonths", "label":"Contract months", "type":"number", "source":"request.context.contractMonths"})
    table(rules,"price")["rows"].append(row("long-term-price", {"monthlyPrice":"15.00", "setupPrice":"0.00"},
                                               [{"column":"contractMonths", "operator":"gte", "value":24}]))
    result = build_result({**REQUEST, "context":{"contractMonths":24}}, PROPOSAL, rules=rules)
    assert result["quote"]["quoteTotalPrice"][0]["price"]["dutyFreeAmount"]["value"] == "15.00"
    with pytest.raises(ValidationError, match="needs information: contractMonths"):
        build_result(REQUEST, PROPOSAL, rules=rules)


def test_discount_snapshot_and_approval_do_not_double_apply():
    rules = load_rules()
    table(rules, "discount")["rows"].append(row("standard-promotion", {"discountPercent":"10.00"}))
    pending = build_result(REQUEST, PROPOSAL, rules=rules)
    assert pending["status"] == "PENDING_APPROVAL" and pending["productOrder"] is None
    assert pending["quote"]["quoteTotalPrice"][0]["price"]["dutyFreeAmount"]["value"] == "10.80"
    table(rules, "price")["defaultOutcome"]["monthlyPrice"] = "99.00"
    approved = approve_result(pending, "human@example.com", "approve")
    assert approved["status"] == "APPROVED" and approved["serviceOrder"] is not None
    assert approved["quote"]["quoteTotalPrice"][0]["price"]["dutyFreeAmount"]["value"] == "10.80"
    assert approved["rulesDigest"] == pending["rulesDigest"]


def test_approval_threshold_is_a_table_value_and_exception_still_holds():
    rules = load_rules()
    table(rules, "discount")["defaultOutcome"] = {"discountPercent":"5.00"}
    table(rules, "approval")["rows"][1]["conditions"][0]["value"] = 10
    result = build_result(REQUEST, PROPOSAL, rules=rules)
    assert result["status"] == "VALIDATED"
    assert result["quote"]["quoteTotalPrice"][0]["price"]["dutyFreeAmount"]["value"] == "11.40"
    assert build_result(REQUEST, {**PROPOSAL,"exceptionRequested":True}, rules=rules)["status"] == "PENDING_APPROVAL"


def test_equal_priority_conflict_blocks_instead_of_row_order_winning():
    rules = load_rules()
    table(rules,"price")["rows"] = [row("a", {"monthlyPrice":"10.00", "setupPrice":"0.00"}),
                                     row("b", {"monthlyPrice":"20.00", "setupPrice":"0.00"})]
    with pytest.raises(ValidationError, match="Conflicting rows"):
        build_result(REQUEST, PROPOSAL, rules=rules)


def test_effective_price_boundaries_are_start_inclusive_end_exclusive():
    rules = load_rules()
    table(rules,"price")["rows"] = [row("dated", {"monthlyPrice":"22.50", "setupPrice":"0.00"},
                                         effectiveFrom="2027-04-01", effectiveTo="2028-04-01")]
    for stamp, expected in [("2027-03-31T23:59:59+00:00","12.00"),("2027-04-01T00:00:00+00:00","22.50"),
                            ("2028-04-01T00:00:00+00:00","12.00")]:
        result=build_result(REQUEST,PROPOSAL,rules=rules,as_of=datetime.fromisoformat(stamp))
        assert result["quote"]["quoteItem"][0]["pricingDecision"]["baseMonthlyPrice"] == expected


def test_missing_operand_on_a_disproved_row_does_not_block_unrelated_customer():
    rules=load_rules()
    rules["columns"].append({"id":"tenure","label":"Tenure","type":"number","source":"request.context.tenure"})
    table(rules,"price")["rows"]=[row("business-only",{"monthlyPrice":"5.00","setupPrice":"0.00"},
                                        [{"column":"segment","operator":"eq","value":"business"},
                                         {"column":"tenure","operator":"gt","value":2}])]
    assert build_result(REQUEST,PROPOSAL,rules=rules)["status"] == "VALIDATED"


@pytest.mark.parametrize("change", [
    lambda r: table(r,"discount")["defaultOutcome"].update(discountPercent="NaN"),
    lambda r: table(r,"approval")["rows"][0]["conditions"][0].update(operator="eval"),
    lambda r: r["columns"][0].update(source="__import__('os')"),
    lambda r: r["columns"].pop(0),
    lambda r: table(r,"price")["rows"].append(row("bad-date",{"monthlyPrice":"2.00","setupPrice":"0.00"}, effectiveFrom="2027-01-01T12:00:00")),
    lambda r: table(r,"price").update(kind=[]),
    lambda r: table(r,"eligibility")["rows"][0]["conditions"][0].update(valueFrom=[]),
    lambda r: table(r,"price")["defaultOutcome"].update(monthlyPrice={"column":[]}),
    lambda r: table(r,"price")["rows"].append(row("bad-date-type",{"monthlyPrice":"2.00","setupPrice":"0.00"}, effectiveFrom=False)),
])
def test_bad_configuration_is_rejected(change):
    rules=load_rules()
    change(rules)
    # Removing a column is invalid only if a row still refers to it.
    if not any(c["id"]=="offerId" for c in rules["columns"]):
        table(rules,"eligibility")["rows"][0]["conditions"].append({"column":"offerId","operator":"eq","value":"po-mobile-mini"})
    with pytest.raises(RuleError):
        validate_rules(rules)


def test_rule_api_edits_apply_to_quote_and_stale_save_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(ui,"RULE_DRAFT",tmp_path/"rules.json")
    monkeypatch.setattr(ui,"DRAFT",tmp_path/"catalogue.json")
    client=ui.app.test_client()
    rules=client.get('/api/rules').json
    old=copy.deepcopy(rules)
    rules["columns"].append({"id":"contractMonths","label":"Contract months","type":"number","source":"request.context.contractMonths"})
    table(rules,"price")["rows"].append(row("contract-price",{"monthlyPrice":"15.00","setupPrice":"0.00"},
                                              [{"column":"contractMonths","operator":"eq","value":24}]))
    table(rules,"discount")["defaultOutcome"]={"discountPercent":"5.00"}
    saved=client.put('/api/rules',json=rules)
    assert saved.status_code==200 and saved.json["version"]!=old["version"]
    assert client.put('/api/rules',json=old).status_code==409
    quoted=client.post('/api/preview',json={**REQUEST,"productOfferingId":"po-mobile-mini","context":{"contractMonths":24}})
    assert quoted.status_code==200 and quoted.json["status"]=="PENDING_APPROVAL"
    assert quoted.json["quote"]["quoteTotalPrice"][0]["price"]["dutyFreeAmount"]["value"]=="14.25"
    assert quoted.json["ruleDecisions"][1]["rowId"]=="contract-price"
    assert "ruleSnapshot" not in quoted.json and "serviceOrder" not in quoted.json
    invalid=copy.deepcopy(saved.json)
    table(invalid,"discount")["defaultOutcome"]={"discountPercent":"101"}
    assert client.put('/api/rules',json=invalid).status_code==400
    assert client.get('/api/rules').json["version"]==saved.json["version"]


def test_eligibility_and_rejection_are_table_driven():
    rules=load_rules()
    table(rules,"eligibility")["rows"].append(row("deny-business",{"eligible":False},
                                                    [{"column":"segment","operator":"eq","value":"business"}],priority=200))
    with pytest.raises(ValidationError,match="ineligible"):
        build_result({**REQUEST,"segment":"business"},PROPOSAL,rules=rules)
    table(rules,"approval")["defaultOutcome"]={"decision":"reject"}
    with pytest.raises(ValidationError,match="rejected by policy"):
        build_result(REQUEST,PROPOSAL,rules=rules)


def test_requested_discount_uses_supported_precision_before_snapshotting():
    with pytest.raises(ValidationError, match="invalid discount"):
        build_result(REQUEST, {**PROPOSAL, "discountPercent":"1.001"})
