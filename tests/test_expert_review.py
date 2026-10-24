"""Expert review cases, grouped by TM Forum area.

IDs match the test plan in TEST_PLAN.md. Cases marked FAULT reproduced a defect before
the fix in the same change; the rest are regression guards for behaviour that was correct.
"""

import base64
import copy
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

import email_core
from business_rules import load_rules
from catalogue_assistant import apply_patch, initial_state
from catalogue_core import DEFAULT_CATALOGUE, ValidationError, approve_result, build_result, validate_catalogue
from contract_core import contract_pdf
from cpq_core import configure_quote
from customer_core import CustomerError, load_customers, validate_customer
from email_core import DeliveryError
from function import main as fn
from ui import app as ui

CUSTOMER = load_customers()["customers"][0]
MINI = {"offeringId": "po-mobile-mini", "termMonths": 12}
SMS = {"offeringId": "po-sms-extra", "termMonths": 12}
REQUEST = {"requestId": "expert-1", "customerId": CUSTOMER["id"], "segment": "consumer", "text": "Mobile Mini"}
TMF648_QUOTE_STATES = {"rejected", "pending", "inProgress", "cancelled", "approved", "accepted"}


def recurring(prices):
    return next(p for p in prices if p["priceType"] == "recurring")["price"]["dutyFreeAmount"]["value"]


def table(rules, kind):
    return next(t for t in rules["tables"] if t["kind"] == kind)


def row(rid, outcome, conditions, priority=100):
    return {"id": rid, "enabled": True, "priority": priority, "conditions": conditions,
            "outcome": outcome, "reason": "Expert review rule"}


def ordered(client, selections=None):
    customer = client.get("/api/cpq/options").json["customer"]
    quote = client.post("/api/cpq/quote", json={"customerId": customer["id"], "selections": selections or [MINI, SMS]})
    assert quote.status_code == 200, quote.json
    payload = client.get(f"/api/cpq/quotes/{quote.json['quote']['id']}/order-payload").json["productOrder"]
    return quote.json, payload


# --- HYG: test hygiene -------------------------------------------------------------------

def test_hyg_01_tests_never_touch_real_ui_state():
    """FAULT: several tests wrote quotes into the real ui/quotes.json."""
    for path in (ui.DRAFT, ui.RULE_DRAFT, ui.CUSTOMER_DRAFT, ui.QUOTE_DRAFT, ui.ORDER_DRAFT):
        assert ui.HERE not in path.parents


# --- CAT: TMF620 catalogue and TMF633 PS -> CFS realization -----------------------------

def test_cat_01_leaf_unit_must_match_its_cfs_unit():
    """FAULT: a 1 TB data leaf mapped to the GB data CFS would provision 1 GB."""
    catalogue = copy.deepcopy(DEFAULT_CATALOGUE)
    next(s for s in catalogue["productSpecifications"] if s["id"] == "ps-data")["unit"] = "TB"
    with pytest.raises(ValidationError, match="unit"):
        validate_catalogue(catalogue)


def test_cat_02_product_manager_cannot_inherit_a_cfs_mapping_with_another_unit():
    """FAULT: PUT /api/catalogue copies the CFS mapping from any leaf with the same characteristic."""
    client = ui.app.test_client()
    catalogue = client.get("/api/catalogue").json
    catalogue["productSpecifications"] += [
        {"id": "ps-data-tb", "name": "Data in TB", "characteristic": "dataGb", "unit": "TB"},
        {"id": "ps-big", "name": "Big data bundle", "isBundle": True, "bundledProductSpecification": [{"id": "ps-data-tb", "value": 1}]}]
    catalogue["productOfferings"].append({"id": "po-big", "name": "Big", "lifecycleStatus": "Draft", "monthlyPrice": "30.00",
                                          "setupPrice": "0.00", "allowedSegments": ["consumer"], "productSpecification": {"id": "ps-big"}})
    response = client.put("/api/catalogue", json=catalogue)
    assert response.status_code == 400 and "unit" in response.json["error"]


@pytest.mark.parametrize("damage", [
    lambda c: c["productOfferings"].append("not-an-object"),
    lambda c: c["productSpecifications"].append(5),
    lambda c: c.update(productOfferings={"po-x": {}}),
])
def test_cat_03_malformed_catalogue_save_is_a_400_not_a_crash(damage):
    """FAULT: non-object rows raised AttributeError, so Flask returned HTTP 500."""
    client = ui.app.test_client()
    catalogue = client.get("/api/catalogue").json
    damage(catalogue)
    assert client.put("/api/catalogue", json=catalogue).status_code == 400


@pytest.mark.parametrize("refs", [[{"id": "ps-mobile-plus", "value": 1}], [{"id": "ps-mobile-mini", "value": 1}]])
def test_cat_04_nested_or_self_referencing_bundles_are_rejected(refs):
    catalogue = copy.deepcopy(DEFAULT_CATALOGUE)
    catalogue["productSpecifications"][3]["bundledProductSpecification"] = refs
    with pytest.raises(ValidationError, match="nested bundle"):
        validate_catalogue(catalogue)


def test_cat_05_product_manager_cannot_smuggle_service_design():
    client = ui.app.test_client()
    catalogue = client.get("/api/catalogue").json
    catalogue["serviceSpecifications"] = [{"id": "cfs-evil", "name": "x", "targetSystem": "x", "operation": "x", "unit": "x"}]
    catalogue["productSpecifications"][0]["serviceSpecificationIds"] = ["cfs-evil"]
    assert client.put("/api/catalogue", json=catalogue).status_code == 200
    saved = ui.current_catalogue()
    assert [s["id"] for s in saved["serviceSpecifications"]] == ["cfs-voice", "cfs-data", "cfs-sms"]
    assert saved["productSpecifications"][0]["serviceSpecificationIds"] == ["cfs-voice"]


# --- RUL: decision tables --------------------------------------------------------------

def test_rul_01_discount_rounds_per_item_then_sums():
    pending = build_result(REQUEST, {"productOfferingIds": ["po-mobile-mini", "po-sms-extra"], "discountPercent": "33.33"})
    items = [recurring(i["itemPrice"]) for i in pending["quote"]["quoteItem"]]
    assert items == ["8.00", "1.67"]  # 8.0004 and 1.66675, each rounded half-up
    assert recurring(pending["quote"]["quoteTotalPrice"]) == "9.67"


def test_rul_02_exists_false_and_not_in_operators():
    rules = load_rules()
    rules["columns"].append({"id": "tier", "label": "Loyalty tier", "type": "string", "source": "request.context.tier"})
    table(rules, "price")["rows"] = [
        row("no-tier", {"monthlyPrice": "13.00", "setupPrice": "0.00"}, [{"column": "tier", "operator": "exists", "value": False}], 200),
        row("not-gold", {"monthlyPrice": "11.00", "setupPrice": "0.00"}, [{"column": "tier", "operator": "notIn", "value": ["gold"]}])]
    price = lambda ctx: build_result({**REQUEST, "context": ctx}, {"productOfferingIds": ["po-mobile-mini"]}, rules=rules)[
        "quote"]["quoteItem"][0]["pricingDecision"]["baseMonthlyPrice"]
    assert price({}) == "13.00"
    assert price({"tier": "silver"}) == "11.00"
    assert price({"tier": "gold"}) == "12.00"


def test_rul_03_disproved_high_priority_row_falls_through():
    rules = load_rules()
    table(rules, "price")["rows"] = [
        row("business", {"monthlyPrice": "9.00", "setupPrice": "0.00"}, [{"column": "segment", "operator": "eq", "value": "business"}], 300),
        row("everyone", {"monthlyPrice": "10.00", "setupPrice": "0.00"}, [], 100)]
    result = build_result(REQUEST, {"productOfferingIds": ["po-mobile-mini"]}, rules=rules)
    assert result["ruleDecisions"][1]["rowId"] == "everyone"


def test_rul_04_approval_helper_needs_a_pending_quote_and_records_rejection():
    validated = build_result(REQUEST, {"productOfferingIds": ["po-mobile-mini"]})
    with pytest.raises(ValidationError):
        approve_result(validated, "reviewer@example.com", "approve")
    pending = build_result(REQUEST, {"productOfferingIds": ["po-mobile-mini"], "discountPercent": 5})
    rejected = approve_result(pending, "reviewer@example.com", "reject")
    assert rejected["status"] == "REJECTED" and rejected["quote"]["state"] == "rejected" and rejected["productOrder"] is None


# --- CPQ: TMF648 quote, TMF679 qualification, TMF671 promotion -------------------------

def test_cpq_01_quote_states_use_the_tmf648_enumeration():
    """FAULT: quotes used 'draft' and 'pendingApproval', which TMF648 v4 QuoteStateType does not define."""
    assert configure_quote(CUSTOMER, [MINI])["quote"]["state"] == "approved"
    assert configure_quote(CUSTOMER, [MINI], "welcome")["quote"]["state"] == "pending"
    assert build_result(REQUEST, {"productOfferingIds": ["po-mobile-mini"], "discountPercent": 5})["quote"]["state"] == "pending"
    assert build_result(REQUEST, {"productOfferingIds": ["po-mobile-mini"]})["quote"]["state"] in TMF648_QUOTE_STATES


def test_cpq_02_quote_declares_a_validity_period():
    """FAULT: quotes had no TMF648 validFor, so a quote could be ordered at any later date."""
    when = datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc)
    quote = configure_quote(CUSTOMER, [MINI], as_of=when)["quote"]
    assert quote["validFor"] == {"startDateTime": when.isoformat(), "endDateTime": (when + timedelta(days=30)).isoformat()}


def test_cpq_03_commitment_estimate_uses_each_items_own_term():
    result = configure_quote(CUSTOMER, [{**MINI, "termMonths": 9}, {**SMS, "termMonths": 16}])
    assert result["commitmentEstimate"] == "158.00"  # 14.00 x 9 + 2.00 x 16


def test_cpq_04_promotion_is_attributed_only_to_promoted_items():
    result = configure_quote(CUSTOMER, [MINI, SMS], "welcome")
    assert [i["pricingDecision"]["promotionId"] for i in result["quote"]["quoteItem"]] == ["welcome", None]
    with pytest.raises(ValidationError, match="Unknown promotion"):
        configure_quote(CUSTOMER, [MINI], "black-friday")


def test_cpq_05_segment_qualification_blocks_ineligible_customer():
    catalogue = copy.deepcopy(DEFAULT_CATALOGUE)
    catalogue["productOfferings"][0]["allowedSegments"] = ["consumer"]
    with pytest.raises(ValidationError, match="ineligible"):
        configure_quote({**CUSTOMER, "segment": "business"}, [MINI], catalogue=catalogue)


# --- ORD: TMF622 product order, TMF641 service order, contract -------------------------

def test_ord_01_expired_quote_cannot_be_ordered(monkeypatch):
    """FAULT: a validated quote stayed orderable forever while catalogue/rules were unchanged."""
    client = ui.app.test_client()
    _, payload = ordered(client, [MINI])
    later = datetime.now(timezone.utc) + timedelta(days=31)

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return later

    monkeypatch.setattr(ui, "datetime", Later)
    response = client.post("/tmf-api/productOrderingManagement/v5/productOrder", json=payload)
    assert response.status_code == 400 and "expired" in response.json["error"]


def test_ord_02_tmf_routes_return_tmf630_error_bodies():
    """FAULT: /tmf-api errors were {'error': ...} instead of the TMF Error resource."""
    client = ui.app.test_client()
    bad = client.post("/tmf-api/productOrderingManagement/v5/productOrder", json={})
    assert bad.status_code == 400
    assert {"code", "reason", "message", "status", "@type"} <= set(bad.json) and bad.json["@type"] == "Error"
    assert bad.json["status"] == "400" and bad.json["error"] == bad.json["message"]
    missing = client.get("/tmf-api/productOrderingManagement/v5/productOrder/MOB-0000-01012026-0001")
    assert missing.status_code == 404 and missing.json["@type"] == "Error" and missing.json["code"] == "404"


def test_ord_03_order_totals_and_terms_match_the_quote():
    client = ui.app.test_client()
    _, payload = ordered(client, [{**MINI, "termMonths": 16}, {**SMS, "termMonths": 9}])
    item_total = sum(Decimal(recurring(i["itemPrice"])) for i in payload["productOrderItem"])
    assert Decimal(recurring(payload["orderTotalPrice"])) == item_total == Decimal("14.00")
    assert [i["itemTerm"][0]["duration"] for i in payload["productOrderItem"]] == [
        {"amount": 16, "units": "month"}, {"amount": 9, "units": "month"}]


def test_ord_04_unknown_quote_reference_is_rejected():
    client = ui.app.test_client()
    response = client.post("/tmf-api/productOrderingManagement/v5/productOrder", json={"quote": [{"id": "quote-nope"}]})
    assert response.status_code == 400 and "not found" in response.json["error"]


def test_ord_05_contract_pdf_has_valid_xref_and_escaped_text():
    client = ui.app.test_client()
    _, payload = ordered(client, [MINI])
    order = client.post("/tmf-api/productOrderingManagement/v5/productOrder", json=payload).json
    record = client.get(f"/api/cpq/orders/{order['id']}").json
    record["customer"]["givenName"] = "Jo (Test) \\"
    pdf = contract_pdf(record)
    assert b"Jo \\(Test\\) \\\\" in pdf
    xref = int(pdf.rsplit(b"startxref\n", 1)[1].split(b"\n")[0])
    lines = pdf[xref:].split(b"\n")
    count = int(lines[1].split()[1])
    for number, entry in enumerate(lines[3:3 + count - 1], 1):
        assert pdf[int(entry[:10]):].startswith(f"{number} 0 obj".encode())


# --- EML: draft contract delivery ------------------------------------------------------

@pytest.mark.parametrize("address", ["jason@mail.example.com", "jason@example.org", "jason@EXAMPLE.NET"])
def test_eml_01_all_reserved_example_domains_are_refused(address):
    """FAULT: only the exact domain example.com was refused (RFC 2606 reserves .org/.net and subdomains)."""
    with pytest.raises(DeliveryError, match="fictional"):
        email_core._recipients(address, None)


@pytest.mark.parametrize("address", ["a,b@customer.test", "a@b.test;c@d.test", "<a@b.test>", '"a"@b.test'])
def test_eml_02_address_lists_and_header_syntax_are_refused(address):
    """FAULT: 'a,b@customer.test' passed and became two To: recipients in the Gmail raw message."""
    with pytest.raises(DeliveryError):
        email_core._recipients(address, None)


# --- AGT: Pub/Sub function and agent ---------------------------------------------------

class _Blob:
    def __init__(self, objects, name):
        self.objects, self.name = objects, name

    def exists(self):
        return self.name in self.objects

    def upload_from_string(self, body, **kwargs):
        if self.name in self.objects:
            raise fn.PreconditionFailed("exists")
        self.objects[self.name] = json.loads(body)

    def download_as_text(self):
        return json.dumps(self.objects[self.name])


class _Storage:
    def __init__(self):
        self.objects = {}

    def bucket(self, name):
        return type("Bucket", (), {"blob": lambda _, n: _Blob(self.objects, n)})()


class _Publisher:
    def __init__(self, events):
        self.events = events

    def publish(self, topic, body):
        self.events.append(json.loads(body))
        return type("Future", (), {"result": lambda self, timeout: "ok"})()


class _Event:
    def __init__(self, payload):
        self.data = {"message": {"data": base64.b64encode(json.dumps(payload).encode()).decode()}}

    def __getitem__(self, key):
        return "event-1"


@pytest.fixture
def cloud(monkeypatch):
    storage, events = _Storage(), []
    monkeypatch.setattr(fn.storage, "Client", lambda **kwargs: storage)
    monkeypatch.setattr(fn.pubsub_v1, "PublisherClient", lambda: _Publisher(events))
    return storage, events


def test_agt_01_bad_rule_configuration_is_rejected_not_retried_forever(cloud, monkeypatch):
    """FAULT: RuleError escaped the handler; with RETRY_POLICY_RETRY and no dead-letter topic it looped."""
    storage, events = cloud
    monkeypatch.setattr(fn, "current_configuration", lambda: (_ for _ in ()).throw(fn.RuleError("bad saved rules")))
    fn.handle_request(_Event(REQUEST))
    assert events[0]["status"] == "REJECTED"
    assert "bad saved rules" in next(iter(storage.objects.values()))["error"]


def test_agt_02_duplicate_delivery_does_not_call_the_model_again(cloud, monkeypatch):
    """FAULT: every redelivery paid for another model call before discovering the stored result."""
    calls = []
    monkeypatch.setattr(fn, "call_agent", lambda request, *_: calls.append(1) or {"productOfferingIds": ["po-mobile-mini"]})
    fn.handle_request(_Event(REQUEST))
    fn.handle_request(_Event(REQUEST))
    assert len(calls) == 1 and len(cloud[1]) == 2


def test_agt_03_model_sees_only_active_offers_and_no_service_design(monkeypatch):
    """FAULT: Draft/Retired offers and network targets (HSS, SMSC) were sent to the model."""
    sent = []

    class Session:
        def __init__(self, credentials):
            pass

        def post(self, url, json, headers, timeout):
            sent.append(json)
            return type("Reply", (), {"raise_for_status": lambda s: None, "json": lambda s: {"output": {}}})()

    monkeypatch.setattr(fn.google.auth, "default", lambda scopes: (None, None))
    monkeypatch.setattr(fn, "AuthorizedSession", Session)
    catalogue = copy.deepcopy(DEFAULT_CATALOGUE)
    catalogue["productOfferings"][1]["lifecycleStatus"] = "Retired"
    fn.call_agent(REQUEST, catalogue)
    given = json.loads(sent[0]["input"]["input"])["catalogue"]
    assert [o["id"] for o in given["productOfferings"]] == ["po-mobile-mini", "po-sms-extra"]
    assert "serviceSpecifications" not in given
    assert not any("serviceSpecificationIds" in s for s in given["productSpecifications"])
    assert "ps-mobile-plus" not in {s["id"] for s in given["productSpecifications"]}


@pytest.mark.parametrize("content,expected", [
    ('```json\n{"productOfferingIds": ["po-mobile-mini"]}\n```', ["po-mobile-mini"]),
    ('{"productOfferingIds": ["po-mobile-mini"]}', ["po-mobile-mini"]),
    ("I cannot help with that.", []),
    ('["po-mobile-mini"]', []),
])
def test_agt_04_agent_output_parsing_never_raises(content, expected):
    """FAULT: fenced or non-JSON output raised inside the Agent Runtime (HTTP 500 -> endless retry)."""
    from agent.agent import QuoteAgent

    agent = QuoteAgent()
    agent.model = type("Model", (), {"invoke": lambda self, messages: type("R", (), {"content": content})()})()
    proposal = agent.query(json.dumps({"catalogue": {}, "request": REQUEST}))
    assert isinstance(proposal, dict) and proposal["productOfferingIds"] == expected
    if not expected:
        with pytest.raises(ValidationError):
            build_result(REQUEST, proposal)


def test_agt_05_agent_result_api_hides_service_design_and_snapshots(monkeypatch):
    """FAULT: /api/agent/results returned catalogue, rule and CFS snapshots to the commercial UI."""
    stored = build_result({**REQUEST, "requestId": "web-" + "a" * 32}, {"productOfferingIds": ["po-mobile-mini"]})

    class Blob:
        def download_as_text(self):
            return json.dumps(stored)

    monkeypatch.setenv("RESULT_BUCKET", "results")
    monkeypatch.setattr("google.cloud.storage.Client",
                        lambda: type("C", (), {"bucket": lambda s, n: type("B", (), {"blob": lambda s, k: Blob()})()})())
    body = ui.app.test_client().get("/api/agent/results/web-" + "a" * 32).json
    assert body["status"] == "VALIDATED" and body["quote"]["quoteItem"]
    for hidden in ("catalogueSnapshot", "ruleSnapshot", "cpqPolicySnapshot", "serviceOrder", "request"):
        assert hidden not in body


# --- AST: guided catalogue assistant ---------------------------------------------------

def test_ast_01_null_fields_from_the_model_mean_not_stated():
    """FAULT: a model reply with "name": null was a 400 even when the rest of the answer was usable."""
    state = apply_patch(initial_state(DEFAULT_CATALOGUE), {"name": "Keep me", "monthlyPrice": "9.00"}, DEFAULT_CATALOGUE)
    state = apply_patch(state, {"name": None, "monthlyPrice": None, "setupPrice": "0", "segments": None}, DEFAULT_CATALOGUE)
    assert (state["name"], state["monthlyPrice"], state["setupPrice"], state["segments"]) == ("Keep me", "9.00", "0.00", None)


def test_ast_02_numeric_string_allowances_are_accepted_but_text_is_not():
    """FAULT: an allowance of "2" from the model was rejected instead of read as 2."""
    state = apply_patch(initial_state(DEFAULT_CATALOGUE), {"allowances": {"ps-data": {"include": True, "value": "2"}}}, DEFAULT_CATALOGUE)
    assert state["allowances"]["ps-data"]["value"] == 2
    for bad in ("two", "NaN", "-1"):
        with pytest.raises(ValidationError):
            apply_patch(initial_state(DEFAULT_CATALOGUE), {"allowances": {"ps-data": {"include": True, "value": bad}}}, DEFAULT_CATALOGUE)


# --- CUS: TMF629 customer --------------------------------------------------------------

def test_cus_01_customer_normalisation_and_uk_only_rules():
    record = copy.deepcopy(CUSTOMER)
    record["mobile"] = "+44 7700-900123"
    record["address"]["postcode"] = "ec1a1bb"
    clean = validate_customer(record)
    assert (clean["mobile"], clean["address"]["postcode"]) == ("+447700900123", "EC1A 1BB")
    for change in (lambda r: r["address"].update(countryCode="FR"), lambda r: r.update(nickname="J"),
                   lambda r: r.update(segment="wholesale"), lambda r: r.update(mobile="020 7946 0000")):
        broken = copy.deepcopy(CUSTOMER)
        change(broken)
        with pytest.raises(CustomerError):
            validate_customer(broken)
