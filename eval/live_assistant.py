"""Exercise Gemini-guided product authoring through Cloud Run and CPQ."""

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

    def call(method, path, **kwargs):
        response = session.request(method, base + path, timeout=130, **kwargs)
        response.raise_for_status()
        return response.json()

    name = "Guided Demo " + uuid.uuid4().hex[:6]
    started = call("GET", "/api/catalogue/assistant/start")
    description = (f"Create a mobile product called {name} with 120 UK voice minutes, "
                   "4 GB data and no SMS. Charge 16 pounds per month with no setup fee, for consumers.")
    turn = call("POST", "/api/catalogue/assistant/turn", json={"state": started["state"], "message": description})
    assert turn["ready"], turn
    assert turn["preview"]["monthlyPrice"] == "16.00"
    assert [(row["name"], row["value"]) for row in turn["preview"]["allowances"]] == [
        ("Voice allowance", 120), ("Data allowance", 4)]
    created = call("POST", "/api/catalogue/assistant/draft", json={"state": turn["state"]})
    offer_id = created["offeringId"]
    assert next(row for row in created["catalogue"]["productOfferings"] if row["id"] == offer_id)["lifecycleStatus"] == "Draft"
    before = call("GET", "/api/cpq/options")
    assert all(row["id"] != offer_id for row in before["offers"])
    published = call("POST", f"/api/catalogue/offerings/{offer_id}/publish",
                     json={"version": created["catalogue"]["version"]})
    assert next(row for row in published["productOfferings"] if row["id"] == offer_id)["lifecycleStatus"] == "Active"
    after = call("GET", "/api/cpq/options")
    assert any(row["id"] == offer_id for row in after["offers"])
    quote = call("POST", "/api/cpq/quote", json={
        "customerId": after["customer"]["id"], "selections": [{"offeringId": offer_id, "termMonths": 12}]})
    assert quote["status"] == "VALIDATED", quote
    payload = call("GET", f"/api/cpq/quotes/{quote['quote']['id']}/order-payload")["productOrder"]
    order = call("POST", "/tmf-api/productOrderingManagement/v5/productOrder", json=payload)
    details = call("GET", f"/api/cpq/orders/{order['id']}")
    assert len(details["serviceOrder"]["orderItem"]) == 2
    report = {"offerName": name, "modelTurnReady": True, "draftHiddenFromCpq": True,
              "publishedInCpq": True, "quoteStatus": quote["status"],
              "monthlyPriceGbp": quote["quote"]["quoteTotalPrice"][0]["price"]["dutyFreeAmount"]["value"],
              "orderState": order["state"], "cfsActionCount": 2}
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
