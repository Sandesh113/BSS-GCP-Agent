"""Publish a draft offering, sell it in CPQ, then retire it from new sales."""

from customer_core import load_customers
from ui import app as ui


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "DRAFT", tmp_path / "catalogue.json")
    monkeypatch.setattr(ui, "QUOTE_DRAFT", tmp_path / "quotes.json")
    monkeypatch.setattr(ui, "ORDER_DRAFT", tmp_path / "orders.json")
    return ui.app.test_client()


def _draft_offer(catalogue, bundle_id="ps-mobile-mini"):
    catalogue["productOfferings"].append({
        "id": "po-lifecycle", "name": "Lifecycle Test", "lifecycleStatus": "Draft",
        "monthlyPrice": "12.00", "setupPrice": "0.00", "allowedSegments": ["consumer"],
        "productSpecification": {"id": bundle_id},
    })
    return catalogue


def test_publish_makes_draft_available_in_cpq_and_retire_stops_new_sales(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    customer_id = load_customers()["customers"][0]["id"]
    draft = client.put("/api/catalogue", json=_draft_offer(client.get("/api/catalogue").json))
    assert draft.status_code == 200, draft.json
    assert not any(row["id"] == "po-lifecycle" for row in client.get("/api/cpq/options").json["offers"])
    selection = {"customerId": customer_id, "selections": [{"offeringId": "po-lifecycle", "termMonths": 12}]}
    assert client.post("/api/cpq/quote", json=selection).status_code == 400
    assert client.post("/api/catalogue/offerings/po-lifecycle/publish", json={"version": "stale"}).status_code == 409

    published = client.post("/api/catalogue/offerings/po-lifecycle/publish", json={"version": draft.json["version"]})
    assert published.status_code == 200, published.json
    assert any(row["id"] == "po-lifecycle" for row in client.get("/api/cpq/options").json["offers"])
    quote = client.post("/api/cpq/quote", json=selection)
    assert quote.status_code == 200 and quote.json["status"] == "VALIDATED"
    payload = client.get(f"/api/cpq/quotes/{quote.json['quote']['id']}/order-payload").json["productOrder"]
    order = client.post("/tmf-api/productOrderingManagement/v5/productOrder", json=payload)
    assert order.status_code == 201, order.json

    retired = client.post("/api/catalogue/offerings/po-lifecycle/retire", json={"version": published.json["version"]})
    assert retired.status_code == 200, retired.json
    assert not any(row["id"] == "po-lifecycle" for row in client.get("/api/cpq/options").json["offers"])
    assert client.post("/api/cpq/quote", json=selection).status_code == 400
    assert client.get(f"/api/cpq/orders/{order.json['id']}").status_code == 200
    assert client.post("/api/catalogue/offerings/po-lifecycle/publish", json={"version": retired.json["version"]}).status_code == 400


def test_publish_requires_complete_mapping_and_cannot_be_bypassed_by_save(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    catalogue = client.get("/api/catalogue").json
    catalogue["productSpecifications"].append({
        "id": "ps-empty", "name": "Incomplete bundle", "isBundle": True,
        "bundledProductSpecification": [],
    })
    saved = client.put("/api/catalogue", json=_draft_offer(catalogue, "ps-empty"))
    assert saved.status_code == 200, saved.json
    rejected = client.post("/api/catalogue/offerings/po-lifecycle/publish", json={"version": saved.json["version"]})
    assert rejected.status_code == 400 and "cannot publish" in rejected.json["error"]
    candidate = client.get("/api/catalogue").json
    next(row for row in candidate["productOfferings"] if row["id"] == "po-lifecycle")["lifecycleStatus"] = "Active"
    assert client.put("/api/catalogue", json=candidate).status_code == 400
    assert next(row for row in client.get("/api/catalogue").json["productOfferings"] if row["id"] == "po-lifecycle")["lifecycleStatus"] == "Draft"


def test_new_offer_must_be_saved_as_draft(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    candidate = _draft_offer(client.get("/api/catalogue").json)
    candidate["productOfferings"][-1]["lifecycleStatus"] = "Active"
    response = client.put("/api/catalogue", json=candidate)
    assert response.status_code == 400 and "new offerings start as Draft" in response.json["error"]
