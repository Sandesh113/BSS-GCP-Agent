import copy

import pytest

from bss_core import CATALOGUE, ValidationError, approve_result, build_result, validate_catalogue

REQUEST = {"requestId": "case-1", "customerId": "customer-1", "segment": "consumer",
           "text": "Mobile Mini with 100 voice minutes, 2 GB data and 100 SMS"}


def test_mobile_mini_quote_and_cfs_decomposition():
    result = build_result(REQUEST, {"productOfferingIds": ["po-mobile-mini"]})
    assert result["status"] == "VALIDATED"
    assert result["quote"]["quoteTotalPrice"][0]["price"]["dutyFreeAmount"]["value"] == "12.00"
    actions = result["serviceOrder"]["orderItem"]
    assert [(a["proposedFulfilment"]["targetSystem"], a["proposedFulfilment"]["value"]) for a in actions] == [
        ("HSS", 100), ("Packet Gateway / customer profile", 2), ("SMSC", 100)]


def test_model_cannot_override_catalogue_price_or_allowance():
    result = build_result(REQUEST, {"productOfferingIds": ["po-mobile-mini"], "monthlyPrice": "0.00", "voiceMinutes": 999})
    assert result["quote"]["quoteTotalPrice"][0]["price"]["dutyFreeAmount"]["value"] == "12.00"
    assert result["serviceOrder"]["orderItem"][0]["proposedFulfilment"]["value"] == 100


def test_discount_held_for_human_approval():
    pending = build_result(REQUEST, {"productOfferingIds": ["po-mobile-mini"], "discountPercent": 10})
    assert pending["status"] == "PENDING_APPROVAL"
    assert pending["productOrder"] is None
    approved = approve_result(pending, "reviewer@example.com", "approve")
    assert approved["quote"]["quoteTotalPrice"][0]["price"]["dutyFreeAmount"]["value"] == "10.80"
    assert approved["serviceOrder"] is not None


def test_draft_offering_cannot_be_sold():
    draft = copy.deepcopy(CATALOGUE)
    draft["productOfferings"][0]["lifecycleStatus"] = "Draft"
    with pytest.raises(ValidationError, match="not an active offering"):
        build_result(REQUEST, {"productOfferingIds": ["po-mobile-mini"]}, draft)


def test_broken_composite_reference_rejected():
    bad = copy.deepcopy(CATALOGUE)
    bad["productSpecifications"][-1]["bundledProductSpecification"][0]["id"] = "missing"
    with pytest.raises(ValidationError, match="unknown"):
        validate_catalogue(bad)
