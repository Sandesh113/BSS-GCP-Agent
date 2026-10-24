import copy

from ui import app as ui


def test_product_manager_api_hides_service_design_and_accepts_draft(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "DRAFT", tmp_path / "draft.json")
    client = ui.app.test_client()
    catalogue = client.get("/api/catalogue").json
    assert "serviceSpecifications" not in catalogue
    assert "serviceSpecificationIds" not in catalogue["productSpecifications"][0]
    catalogue["productSpecifications"].append({
        "id": "ps-new", "name": "New allowance", "characteristic": "newAllowance", "unit": "units"
    })
    saved = client.put("/api/catalogue", json=catalogue)
    assert saved.status_code == 200
    assert "serviceSpecifications" not in saved.json
    assert ui.current_catalogue()["productSpecifications"][-1]["serviceSpecificationIds"] == []
    quote = client.post("/api/preview", json={"customerId": "c", "segment": "consumer", "text": "Mobile Mini",
                                               "productOfferingId": "po-mobile-mini"})
    assert quote.status_code == 200
    assert "serviceOrder" not in quote.json
    assert "catalogueSnapshot" not in quote.json
