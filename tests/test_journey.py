"""Local contract tests from catalogue publication through CPQ and CFS actions."""

import copy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from catalogue_core import DEFAULT_CATALOGUE, ValidationError, approve_result, build_result, validate_catalogue
import cpq_core
from cpq_core import configure_quote
from customer_core import load_customers
from ui import app as ui


CUSTOMER = load_customers()["customers"][0]
REQUEST = {"requestId": "journey-mini", "customerId": CUSTOMER["id"],
           "segment": "consumer", "text": "100 minutes, 2 GB data and 100 texts"}


def test_seed_journey_from_commercial_catalogue_to_cfs_and_cpq(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "DRAFT", tmp_path / "catalogue.json")
    monkeypatch.setattr(ui, "RULE_DRAFT", tmp_path / "rules.json")
    client = ui.app.test_client()
    commercial = client.get("/api/catalogue").json
    assert "serviceSpecifications" not in commercial
    assert all("serviceSpecificationIds" not in spec for spec in commercial["productSpecifications"])

    options = client.get("/api/cpq/options").json
    assert options["customer"]["id"] == CUSTOMER["id"]
    mini = next(offer for offer in options["offers"] if offer["id"] == "po-mobile-mini")
    assert [(item["characteristic"], item["value"]) for item in mini["allowances"]] == [
        ("voiceMinutes", 100), ("dataGb", 2), ("smsCount", 100)]

    cpq = client.post("/api/cpq/quote", json={"customerId": CUSTOMER["id"], "selections": [
        {"offeringId": "po-mobile-mini", "termMonths": 12},
        {"offeringId": "po-sms-extra", "termMonths": 12}]}).json
    assert cpq["status"] == "VALIDATED"
    assert cpq["quote"]["quoteTotalPrice"][0]["price"]["dutyFreeAmount"]["value"] == "14.50"

    agent_result = build_result(REQUEST, {"productOfferingIds": ["po-mobile-mini"]})
    assert [item["productSpecification"]["id"] for item in agent_result["quote"]["quoteItem"][0]["product"]["productCharacteristic"]] == [
        "ps-voice", "ps-data", "ps-sms"]
    assert [(item["service"]["serviceSpecification"]["id"], item["proposedFulfilment"]["value"])
            for item in agent_result["serviceOrder"]["orderItem"]] == [
                ("cfs-voice", 100), ("cfs-data", 2), ("cfs-sms", 100)]


def test_new_composite_offer_flows_from_catalogue_save_into_cpq_and_agent(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "DRAFT", tmp_path / "catalogue.json")
    monkeypatch.setattr(ui, "RULE_DRAFT", tmp_path / "rules.json")
    client = ui.app.test_client()
    commercial = client.get("/api/catalogue").json
    commercial["productSpecifications"].append({
        "id": "ps-eval-data", "name": "Evaluation data bundle", "isBundle": True,
        "bundledProductSpecification": [{"id": "ps-data", "value": 5}]})
    commercial["productOfferings"].append({
        "id": "po-eval-data", "name": "Evaluation Data", "lifecycleStatus": "Draft",
        "monthlyPrice": "8.75", "setupPrice": "0.00", "allowedSegments": ["consumer"],
        "productSpecification": {"id": "ps-eval-data"}})
    saved = client.put("/api/catalogue", json=commercial)
    assert saved.status_code == 200, saved.json
    assert not any(offer["id"] == "po-eval-data" for offer in client.get("/api/cpq/options").json["offers"])
    publish = client.post("/api/catalogue/offerings/po-eval-data/publish", json={"version": saved.json["version"]})
    assert publish.status_code == 200, publish.json
    assert any(offer["id"] == "po-eval-data" for offer in client.get("/api/cpq/options").json["offers"])
    quote = client.post("/api/cpq/quote", json={"customerId": CUSTOMER["id"], "selections": [
        {"offeringId": "po-eval-data", "termMonths": 12}]})
    assert quote.status_code == 200, quote.json
    assert quote.json["quote"]["quoteTotalPrice"][0]["price"]["dutyFreeAmount"]["value"] == "8.75"
    result = build_result({**REQUEST, "requestId": "journey-new"},
                          {"productOfferingIds": ["po-eval-data"]}, ui.current_catalogue())
    assert result["serviceOrder"]["orderItem"][0]["service"]["serviceSpecification"]["id"] == "cfs-data"
    assert result["serviceOrder"]["orderItem"][0]["proposedFulfilment"]["value"] == 5


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), 0, -1, True, 1000001])
def test_unusable_allowance_cannot_be_published_or_quoted(value):
    catalogue = copy.deepcopy(DEFAULT_CATALOGUE)
    catalogue["productSpecifications"][3]["bundledProductSpecification"][0]["value"] = value
    with pytest.raises(ValidationError, match="invalid allowance"):
        validate_catalogue(catalogue)
    with pytest.raises(ValidationError, match="invalid allowance"):
        build_result(REQUEST, {"productOfferingIds": ["po-mobile-mini"]}, catalogue)


def test_promotion_end_boundary_and_model_price_tampering():
    start = datetime(2026, 12, 1, tzinfo=timezone.utc)
    end = datetime(2027, 1, 1, tzinfo=timezone.utc)
    selected = [{"offeringId": "po-mobile-mini", "termMonths": 12}]
    valid = configure_quote(CUSTOMER, selected, "christmas-2026", as_of=start)
    assert valid["status"] == "PENDING_APPROVAL"
    with pytest.raises(ValidationError, match="not active"):
        configure_quote(CUSTOMER, selected, "christmas-2026", as_of=end)
    result = build_result(REQUEST, {"productOfferingIds": ["po-mobile-mini"],
                                    "monthlyPrice": "0.00", "voiceMinutes": 999999})
    assert result["quote"]["quoteTotalPrice"][0]["price"]["dutyFreeAmount"]["value"] == "12.00"
    assert result["serviceOrder"]["orderItem"][0]["proposedFulfilment"]["value"] == 100


@pytest.mark.parametrize("ids,reason", [
    (["po-sms-extra"], "needs a primary mobile plan"),
    (["po-mobile-mini", "po-mobile-plus"], "one primary mobile plan"),
])
def test_agent_and_cpq_share_product_combination_rules(ids, reason):
    with pytest.raises(ValidationError, match=reason):
        build_result(REQUEST, {"productOfferingIds": ids})


def test_approval_uses_original_product_policy_snapshot(monkeypatch):
    pending = build_result(REQUEST, {"productOfferingIds": ["po-mobile-mini"], "discountPercent": 10})
    assert pending["status"] == "PENDING_APPROVAL"
    monkeypatch.setattr(cpq_core, "load_policy", lambda: (_ for _ in ()).throw(AssertionError("current policy loaded")))
    approved = approve_result(pending, "reviewer@example.com", "approve")
    assert approved["status"] == "APPROVED"
    assert approved["cpqPolicySnapshot"] == pending["cpqPolicySnapshot"]


def test_cloud_function_archive_includes_shared_policy_dependencies():
    manifest = (Path(__file__).resolve().parents[1] / "infra" / "workload" / "main.tf").read_text(encoding="utf-8")
    for filename in ("catalogue_core.py", "product_constraints.py", "cpq_core.py",
                     "cpq_policy.json", "customer_core.py"):
        assert f'filename = "{filename}"' in manifest


@pytest.mark.parametrize("proposal", [
    {"productOfferingIds": []},
    {"productOfferingIds": ["po-mobile-mini", "po-mobile-mini"]},
    {"productOfferingIds": ["po-does-not-exist"]},
    {"productOfferingIds": ["po-mobile-mini"], "discountPercent": 101},
    {"productOfferingIds": ["po-mobile-mini"], "exceptionRequested": "yes"},
])
def test_invalid_agent_proposal_never_creates_an_order(proposal):
    with pytest.raises(ValidationError):
        build_result(REQUEST, proposal)
