import copy
from datetime import datetime, timezone

import pytest

from catalogue_core import DEFAULT_CATALOGUE, ValidationError
from cpq_core import configure_quote, load_policy
from customer_core import CustomerError, load_customers, validate_customer
from ui import app as ui

CUSTOMER = load_customers()["customers"][0]
MINI = {"offeringId": "po-mobile-mini", "termMonths": 12}
SMS = {"offeringId": "po-sms-extra", "termMonths": 12}
PLUS = {"offeringId": "po-mobile-plus", "termMonths": 12}


def monthly(result):
    return result["quote"]["quoteTotalPrice"][0]["price"]["dutyFreeAmount"]["value"]


def test_uk_customers_are_synthetic_and_essential_fields_are_checked():
    assert len(load_customers()["customers"]) == 1
    assert (CUSTOMER["givenName"], CUSTOMER["familyName"]) == ("Jason", "Smith")
    assert all(c["email"].endswith("@example.com") and c["address"]["countryCode"] == "GB" for c in load_customers()["customers"])
    for field, value in (("mobile", "12345"), ("email", "invalid")):
        broken = copy.deepcopy(CUSTOMER)
        broken[field] = value
        with pytest.raises(CustomerError):
            validate_customer(broken)
    broken = copy.deepcopy(CUSTOMER)
    broken["address"]["postcode"] = "not-a-postcode"
    with pytest.raises(CustomerError, match="postcode"):
        validate_customer(broken)


def test_two_compatible_products_have_separate_terms_and_item_prices():
    result = configure_quote(CUSTOMER, [MINI, SMS])
    assert result["status"] == "VALIDATED"
    assert result["quote"]["state"] == "draft"
    assert [item["productOffering"]["id"] for item in result["quote"]["quoteItem"]] == ["po-mobile-mini", "po-sms-extra"]
    assert monthly(result) == "14.50"
    assert result["commitmentEstimate"] == "174.00"
    assert result["quote"]["relatedParty"] == [{"id": CUSTOMER["id"], "role": "customer"}]


def test_product_constraints_block_conflicts_and_unanchored_addons():
    with pytest.raises(ValidationError, match="one primary mobile plan"):
        configure_quote(CUSTOMER, [MINI, PLUS])
    with pytest.raises(ValidationError, match="needs a primary mobile plan"):
        configure_quote(CUSTOMER, [SMS])
    with pytest.raises(ValidationError, match="one of each offering"):
        configure_quote(CUSTOMER, [MINI, MINI])


def test_term_lookup_changes_price_and_invalid_term_is_rejected():
    short = configure_quote(CUSTOMER, [{**MINI, "termMonths": 9}])
    long = configure_quote(CUSTOMER, [{**MINI, "termMonths": 16}])
    assert monthly(short) == "14.00"
    assert monthly(long) == "11.00"
    with pytest.raises(ValidationError, match="does not offer"):
        configure_quote(CUSTOMER, [{**MINI, "termMonths": 8}])


def test_edited_term_row_changes_next_quote_without_python_change():
    policy = load_policy()
    next(row for row in policy["termPrices"] if row["offeringId"] == MINI["offeringId"] and row["months"] == 12)["monthlyPrice"] = "13.25"
    assert monthly(configure_quote(CUSTOMER, [MINI], policy=policy)) == "13.25"


def test_christmas_promotion_is_dated_and_requires_review():
    december = datetime(2026, 12, 15, tzinfo=timezone.utc)
    result = configure_quote(CUSTOMER, [MINI, SMS], "christmas-2026", as_of=december)
    assert result["status"] == "PENDING_APPROVAL"
    assert monthly(result) == "13.30"
    assert result["quote"]["quoteItem"][0]["pricingDecision"]["discountPercent"] == "10.00"
    assert result["quote"]["quoteItem"][1]["pricingDecision"]["discountPercent"] == "0.00"
    with pytest.raises(ValidationError, match="not active"):
        configure_quote(CUSTOMER, [MINI], "christmas-2026", as_of=datetime(2026, 11, 30, tzinfo=timezone.utc))


def test_new_catalogue_offer_can_enter_cpq_at_default_twelve_month_term():
    catalogue = copy.deepcopy(DEFAULT_CATALOGUE)
    new_offer = copy.deepcopy(catalogue["productOfferings"][0])
    new_offer.update(id="po-test-new", name="Test New", monthlyPrice="7.25")
    catalogue["productOfferings"].append(new_offer)
    result = configure_quote(CUSTOMER, [{"offeringId": "po-test-new", "termMonths": 12}], catalogue=catalogue)
    assert monthly(result) == "7.25"


def test_cpq_api_saves_customer_and_validates_multiline_quote(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "CUSTOMER_DRAFT", tmp_path / "customers.json")
    monkeypatch.setattr(ui, "DRAFT", tmp_path / "catalogue.json")
    monkeypatch.setattr(ui, "RULE_DRAFT", tmp_path / "rules.json")
    client = ui.app.test_client()
    assert len(client.get("/api/customers").json["customers"]) == 1
    options = client.get("/api/cpq/options").json
    assert options["customer"]["givenName"] == "Jason"
    assert len(options["offers"]) == 3
    assert options["offers"][0]["termPrices"]["9"] == "14.00"
    assert options["offers"][0]["allowances"][0]["value"] == 100
    new_customer = {k: copy.deepcopy(CUSTOMER[k]) for k in ("givenName", "familyName", "email", "mobile", "address", "segment")}
    new_customer.update(givenName="Taylor", email="taylor.test@example.com")
    created = client.post("/api/customers", json=new_customer)
    assert created.status_code == 201
    assert client.post("/api/customers", json=new_customer).status_code == 400
    quote = client.post("/api/cpq/quote", json={"customerId": created.json["id"], "selections": [MINI, SMS]})
    assert quote.status_code == 200
    assert quote.json["status"] == "VALIDATED" and monthly(quote.json) == "14.50"
    assert "address" not in quote.json["quote"]
    rejected = client.post("/api/cpq/quote", json={"customerId": created.json["id"], "selections": [MINI, PLUS]})
    assert rejected.status_code == 400 and "one primary" in rejected.json["error"]
