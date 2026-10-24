"""Verify Draft -> Publish -> CPQ -> ProductOrder against private Cloud Run."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    session = requests.Session()

    def call(method, path, *, expect=None, **kwargs):
        response = session.request(method, base + path, timeout=60, **kwargs)
        if expect is not None:
            assert response.status_code == expect, (path, response.status_code, response.text[:500])
        else:
            response.raise_for_status()
        return response

    suffix = uuid.uuid4().hex[:8]
    offer_id = f"po-lifecycle-{suffix}"
    spec_id = f"ps-lifecycle-{suffix}"
    catalogue = call("GET", "/api/catalogue").json()
    catalogue["productSpecifications"].append({
        "id": spec_id, "name": "Lifecycle Demo specification", "isBundle": True,
        "bundledProductSpecification": [
            {"id": "ps-voice", "value": 100},
            {"id": "ps-data", "value": 4},
            {"id": "ps-sms", "value": 100},
        ],
    })
    catalogue["productOfferings"].append({
        "id": offer_id, "name": "Lifecycle Demo 4 GB", "lifecycleStatus": "Draft",
        "monthlyPrice": "15.00", "setupPrice": "0.00", "allowedSegments": ["consumer"],
        "productSpecification": {"id": spec_id},
    })
    saved = call("PUT", "/api/catalogue", json=catalogue).json()
    assert next(row for row in saved["productOfferings"] if row["id"] == offer_id)["lifecycleStatus"] == "Draft"
    before = call("GET", "/api/cpq/options").json()
    assert all(row["id"] != offer_id for row in before["offers"])
    selection = {"customerId": before["customer"]["id"],
                 "selections": [{"offeringId": offer_id, "termMonths": 12}]}
    call("POST", "/api/cpq/quote", json=selection, expect=400)

    published = call("POST", f"/api/catalogue/offerings/{offer_id}/publish",
                     json={"version": saved["version"]}).json()
    assert next(row for row in published["productOfferings"] if row["id"] == offer_id)["lifecycleStatus"] == "Active"
    after = call("GET", "/api/cpq/options").json()
    assert any(row["id"] == offer_id for row in after["offers"])
    quote = call("POST", "/api/cpq/quote", json=selection).json()
    assert quote["status"] == "VALIDATED", quote
    assert quote["quote"]["quoteTotalPrice"][0]["price"]["dutyFreeAmount"]["value"] == "15.00"
    payload = call("GET", f"/api/cpq/quotes/{quote['quote']['id']}/order-payload").json()["productOrder"]
    order = call("POST", "/tmf-api/productOrderingManagement/v5/productOrder", json=payload).json()
    details = call("GET", f"/api/cpq/orders/{order['id']}").json()
    assert len(details["serviceOrder"]["orderItem"]) == 3
    pdf = call("GET", f"/api/cpq/orders/{order['id']}/contract.pdf")
    assert pdf.content.startswith(b"%PDF-")

    report = {"offeringId": offer_id, "draftHiddenFromCpq": True, "draftQuoteRejected": True,
              "publishedStatus": "Active", "visibleInCpq": True, "quoteStatus": quote["status"],
              "monthlyPriceGbp": "15.00", "productOrderState": order["state"],
              "cfsActionCount": 3, "draftContractPdfBytes": len(pdf.content)}
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
