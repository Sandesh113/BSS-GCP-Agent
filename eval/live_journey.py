"""Exercise catalogue publication through CPQ, order and cloud agent via an authenticated proxy."""
from __future__ import annotations

import argparse
import copy
import json
import time
from pathlib import Path

import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True, help="Authenticated Cloud Run proxy URL")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    session = requests.Session()

    def call(method, path, **kwargs):
        response = session.request(method, base + path, timeout=130, **kwargs)
        response.raise_for_status()
        return response

    catalogue = call("GET", "/api/catalogue").json()
    # A mismatched leaf/CFS unit must be rejected without changing the saved catalogue.
    invalid = copy.deepcopy(catalogue)
    invalid["productSpecifications"].append({
        "id": "ps-eval-invalid-tb", "name": "Invalid TB mapping", "isBundle": False,
        "characteristic": "dataGb", "unit": "TB", "serviceSpecificationIds": ["cfs-data"],
    })
    rejected = session.put(base + "/api/catalogue", json=invalid, timeout=130)
    assert rejected.status_code == 400 and "unit" in rejected.json()["error"]
    offer_id = "po-cloud-demo-3gb"
    if not any(row["id"] == offer_id for row in catalogue["productOfferings"]):
        catalogue["productSpecifications"].append({
            "id": "ps-cloud-demo-3gb", "name": "Cloud Demo 3 GB", "isBundle": True,
            "bundledProductSpecification": [
                {"id": "ps-voice", "value": 100},
                {"id": "ps-data", "value": 3},
                {"id": "ps-sms", "value": 100},
            ],
        })
        catalogue["productOfferings"].append({
            "id": offer_id, "name": "Cloud Demo 3 GB", "lifecycleStatus": "Draft",
            "monthlyPrice": "13.00", "setupPrice": "0.00",
            "allowedSegments": ["consumer"],
            "productSpecification": {"id": "ps-cloud-demo-3gb"},
        })
        catalogue = call("PUT", "/api/catalogue", json=catalogue).json()
    offer = next(row for row in catalogue["productOfferings"] if row["id"] == offer_id)
    if offer["lifecycleStatus"] == "Draft":
        assert all(row["id"] != offer_id for row in call("GET", "/api/cpq/options").json()["offers"])
        call("POST", f"/api/catalogue/offerings/{offer_id}/publish", json={"version": catalogue["version"]})
    saved = call("GET", "/api/catalogue").json()
    assert any(row["id"] == offer_id for row in saved["productOfferings"])
    options = call("GET", "/api/cpq/options").json()
    assert any(row["id"] == offer_id for row in options["offers"])

    quote = call("POST", "/api/cpq/quote", json={
        "customerId": options["customer"]["id"],
        "selections": [{"offeringId": offer_id, "termMonths": 12}],
        "promotionId": None,
    }).json()
    assert quote["status"] == "VALIDATED", quote
    assert quote["quote"]["state"] == "approved"
    assert quote["quote"]["validFor"]["endDateTime"] > quote["quote"]["validFor"]["startDateTime"]
    prepared = call("GET", f"/api/cpq/quotes/{quote['quote']['id']}/order-payload").json()
    order = call("POST", "/tmf-api/productOrderingManagement/v5/productOrder",
                 json=prepared["productOrder"]).json()
    assert order["id"].startswith("MOB-")
    details = call("GET", f"/api/cpq/orders/{order['id']}").json()
    actions = details["serviceOrder"]["orderItem"]
    assert [row["service"]["serviceSpecification"]["id"] for row in actions] == [
        "cfs-voice", "cfs-data", "cfs-sms"]
    pdf = call("GET", f"/api/cpq/orders/{order['id']}/contract.pdf")
    assert pdf.content.startswith(b"%PDF-")

    submitted = call("POST", "/api/agent/requests", json={
        "customerId": options["customer"]["id"], "segment": "consumer",
        "text": "I want the Cloud Demo 3 GB offer with 100 minutes of voice, 3 GB data and 100 SMS.",
        "context": {},
    }).json()
    agent_result = None
    for _ in range(80):
        time.sleep(3)
        response = call("GET", f"/api/agent/results/{submitted['requestId']}")
        if response.status_code != 202:
            agent_result = response.json()
            break
    assert agent_result is not None, "Cloud agent result did not arrive"
    assert agent_result["status"] == "VALIDATED", agent_result
    assert agent_result["quote"]["quoteItem"][0]["productOffering"]["id"] == offer_id
    assert "serviceOrder" not in agent_result
    assert "catalogue" not in agent_result and "rules" not in agent_result and "policy" not in agent_result
    assert agent_result["quote"]["state"] == "approved"

    report = {
        "catalogueOffer": offer_id, "catalogueVersion": saved["version"],
        "mismatchedUnitRejected": True, "quoteHasValidityPeriod": True,
        "cpqStatus": quote["status"], "productOrderId": order["id"],
        "productOrderState": order["state"], "cfsActionCount": len(actions),
        "contractPdfBytes": len(pdf.content), "agentStatus": agent_result["status"],
        "agentOffer": agent_result["quote"]["quoteItem"][0]["productOffering"]["id"],
        "agentResultCommercialOnly": True,
    }
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
