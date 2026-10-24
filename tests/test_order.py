"""Validated CPQ quote -> TMF622 order -> PS/CFS plan -> draft contract."""

import copy
import base64
from datetime import datetime, timedelta, timezone
from email import message_from_bytes

from order_core import next_mobile_order_id
from ui import app as ui


MINI = {"offeringId": "po-mobile-mini", "termMonths": 12}
SMS = {"offeringId": "po-sms-extra", "termMonths": 12}


def client_with_store(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "DRAFT", tmp_path / "catalogue.json")
    monkeypatch.setattr(ui, "RULE_DRAFT", tmp_path / "rules.json")
    monkeypatch.setattr(ui, "CUSTOMER_DRAFT", tmp_path / "customers.json")
    monkeypatch.setattr(ui, "QUOTE_DRAFT", tmp_path / "quotes.json")
    monkeypatch.setattr(ui, "ORDER_DRAFT", tmp_path / "orders.json")
    return ui.app.test_client()


def validated_quote(client, selections=None, promotion=None):
    customer = client.get("/api/cpq/options").json["customer"]
    response = client.post("/api/cpq/quote", json={"customerId": customer["id"],
                                                    "selections": selections or [MINI, SMS],
                                                    "promotionId": promotion})
    assert response.status_code == 200, response.json
    return response.json


def submit(client, quote):
    prepared = client.get(f"/api/cpq/quotes/{quote['quote']['id']}/order-payload")
    assert prepared.status_code == 200, prepared.json
    response = client.post("/tmf-api/productOrderingManagement/v5/productOrder",
                           json=prepared.json["productOrder"])
    return prepared.json, response


def test_mobile_order_reference_uses_utc_minute_and_next_persisted_sequence():
    moment = datetime(2026, 10, 24, 22, 26, 45, tzinfo=timezone.utc)
    assert next_mobile_order_id([], moment) == "MOB-2226-24102026-0001"
    existing = ["order-a1b2c3", "MOB-2226-24102026-0001", "MOB-2226-24102026-0003",
                "MOB-2225-24102026-0099", "MOB-2226-24102026-invalid"]
    assert next_mobile_order_id(existing, moment) == "MOB-2226-24102026-0004"
    assert next_mobile_order_id(existing, moment + timedelta(minutes=1)) == "MOB-2227-24102026-0001"
    assert next_mobile_order_id([], moment.astimezone(timezone(timedelta(hours=1)))) == "MOB-2226-24102026-0001"


def test_submitted_order_and_contract_share_sequential_reference(tmp_path, monkeypatch):
    moment = datetime(2026, 10, 24, 22, 26, tzinfo=timezone.utc)

    class FixedDateTime:
        @staticmethod
        def now(tz):
            assert tz == timezone.utc
            return moment

    monkeypatch.setattr(ui, "datetime", FixedDateTime)
    client = client_with_store(tmp_path, monkeypatch)
    first_payload, first = submit(client, validated_quote(client, selections=[MINI]))
    assert first.status_code == 201, first.json
    assert first.json["id"] == "MOB-2226-24102026-0001"
    assert first.json["creationDate"] == moment.isoformat()
    assert first.headers["Location"].endswith(first.json["id"])
    replay = client.post("/tmf-api/productOrderingManagement/v5/productOrder", json=first_payload["productOrder"])
    assert replay.status_code == 200 and replay.json["id"] == first.json["id"]

    _, second = submit(client, validated_quote(client, selections=[MINI]))
    assert second.status_code == 201, second.json
    assert second.json["id"] == "MOB-2226-24102026-0002"
    detail = client.get(f"/api/cpq/orders/{second.json['id']}").json
    assert detail["serviceOrder"]["productOrder"]["id"] == second.json["id"]
    pdf = client.get(f"/api/cpq/orders/{second.json['id']}/contract.pdf")
    assert pdf.status_code == 200
    assert second.json["id"].encode() in pdf.data
    assert f"draft-contract-{second.json['id']}.pdf" in pdf.headers["Content-Disposition"]


def test_order_submission_and_cfs_decomposition_are_idempotent(tmp_path, monkeypatch):
    client = client_with_store(tmp_path, monkeypatch)
    quote = validated_quote(client)
    prepared, response = submit(client, quote)
    assert response.status_code == 201, response.json
    payload = prepared["productOrder"]
    assert payload["@type"] == "ProductOrder"
    assert "id" not in payload and "state" not in payload
    assert payload["quote"][0]["id"] == quote["quote"]["id"]
    assert [item["productOffering"]["id"] for item in payload["productOrderItem"]] == [
        "po-mobile-mini", "po-sms-extra"]
    assert all(item["state"] == "acknowledged" for item in payload["productOrderItem"])
    assert all(price["@type"] == "OrderPrice" and price["price"]["@type"] == "Price"
               for item in payload["productOrderItem"] for price in item["itemPrice"])
    assert [item["product"]["productSpecification"]["id"] for item in payload["productOrderItem"]] == [
        "ps-mobile-mini", "ps-sms-extra"]
    order_id = response.json["id"]
    detail = client.get(f"/api/cpq/orders/{order_id}").json
    assert detail["productOrder"]["state"] == "acknowledged"
    assert [item["service"]["serviceSpecification"]["id"] for item in detail["serviceOrder"]["orderItem"]] == [
        "cfs-voice", "cfs-data", "cfs-sms", "cfs-sms"]
    assert [item["productOrderItem"]["id"] for item in detail["serviceOrder"]["orderItem"]] == [
        "1", "1", "1", "2"]
    assert detail["contractReview"]["bindingContractReady"] is False
    pdf = client.get(f"/api/cpq/orders/{order_id}/contract.pdf")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF-1.4")
    assert pdf.mimetype == "application/pdf"
    again = client.post("/tmf-api/productOrderingManagement/v5/productOrder", json=payload)
    assert again.status_code == 200 and again.json["id"] == order_id
    assert len(ui._read_store(ui.ORDER_DRAFT)) == 1
    tampered = copy.deepcopy(payload)
    tampered["productOrderItem"][0]["quantity"] = 999
    assert client.post("/tmf-api/productOrderingManagement/v5/productOrder", json=tampered).status_code == 400


def test_pending_approval_and_stale_catalogue_block_order(tmp_path, monkeypatch):
    client = client_with_store(tmp_path, monkeypatch)
    pending = validated_quote(client, promotion="welcome")
    assert pending["status"] == "PENDING_APPROVAL"
    assert client.get(f"/api/cpq/quotes/{pending['quote']['id']}/order-payload").status_code == 400
    valid = validated_quote(client, selections=[MINI])
    catalogue = client.get("/api/catalogue").json
    catalogue["productOfferings"][0]["monthlyPrice"] = "13.00"
    assert client.put("/api/catalogue", json=catalogue).status_code == 200
    stale = client.get(f"/api/cpq/quotes/{valid['quote']['id']}/order-payload")
    assert stale.status_code == 400 and "validate the quote again" in stale.json["error"]


def test_draft_email_requires_real_recipient_and_smtp_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("MAIL_PROVIDER", "smtp")
    client = client_with_store(tmp_path, monkeypatch)
    _, response = submit(client, validated_quote(client, selections=[MINI]))
    order_id = response.json["id"]
    route = f"/api/cpq/orders/{order_id}/email"
    example = client.post(route, json={"primaryEmail": "jason.smith@example.com"})
    assert example.status_code == 400 and "fictional" in example.json["error"]
    monkeypatch.delenv("SMTP_HOST", raising=False)
    unconfigured = client.post(route, json={"primaryEmail": "jason@customer.test"})
    assert unconfigured.status_code == 400 and "not configured" in unconfigured.json["error"]

    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            assert (host, port) == ("smtp.test", 587)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self, context):
            pass

        def login(self, username, password):
            assert (username, password) == ("user", "secret")

        def send_message(self, message, to_addrs):
            sent.append((message, to_addrs))

    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("SMTP_FROM", "demo@provider.test")
    monkeypatch.setenv("SMTP_USERNAME", "user")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setattr("email_core.smtplib.SMTP", FakeSMTP)
    delivered = client.post(route, json={"primaryEmail": "jason@customer.test", "copyEmail": "owner@provider.test"})
    assert delivered.status_code == 200, delivered.json
    assert delivered.json["recipients"] == ["jason@customer.test", "owner@provider.test"]
    assert sent[0][0].get_content_type() == "multipart/mixed"
    assert sent[0][1] == delivered.json["recipients"]


def test_gmail_contract_delivery_uses_verified_sender_and_deduplicates_copy(tmp_path, monkeypatch):
    client = client_with_store(tmp_path, monkeypatch)
    _, response = submit(client, validated_quote(client, selections=[MINI]))
    route = f"/api/cpq/orders/{response.json['id']}/email"
    monkeypatch.setenv("MAIL_PROVIDER", "gmail")
    monkeypatch.setenv("GMAIL_OAUTH_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setenv("GMAIL_SENDER_EMAIL", "sender@gmail.com")
    calls = []

    class Reply:
        def __init__(self, payload, status_code=200):
            self.payload = payload
            self.status_code = status_code

        def json(self):
            return self.payload

        def raise_for_status(self):
            assert self.status_code < 400

    def profile(url, headers, timeout):
        assert url.endswith("/userinfo")
        assert headers == {"Authorization": "Bearer short-lived-token"}
        return Reply({"email": "sender@gmail.com", "email_verified": True})

    def send(url, headers, json, timeout):
        assert url.endswith("/users/me/messages/send")
        calls.append(json)
        return Reply({"id": "gmail-message-1"})

    monkeypatch.setattr("email_core.requests.get", profile)
    monkeypatch.setattr("email_core.requests.post", send)
    result = client.post(route, json={"primaryEmail": "recipient@gmail.com", "copyEmail": "RECIPIENT@gmail.com",
                                      "gmailAccessToken": "short-lived-token"})
    assert result.status_code == 200, result.json
    assert result.json["recipients"] == ["recipient@gmail.com"]
    assert result.json["sender"] == "sender@gmail.com"
    assert result.json["messageId"] == "gmail-message-1"
    raw = base64.urlsafe_b64decode(calls[0]["raw"])
    message = message_from_bytes(raw)
    assert message["To"] == "recipient@gmail.com"
    assert message["Cc"] is None
    assert any(part.get_filename() == f"draft-contract-{response.json['id']}.pdf"
               and part.get_payload(decode=True).startswith(b"%PDF") for part in message.walk())

    monkeypatch.setattr("email_core.requests.get", lambda *a, **k: Reply({"email": "other@gmail.com", "email_verified": True}))
    refused = client.post(route, json={"primaryEmail": "recipient@gmail.com", "gmailAccessToken": "short-lived-token"})
    assert refused.status_code == 400 and "Connect sender@gmail.com" in refused.json["error"]
    assert len(calls) == 1

    monkeypatch.setattr("email_core.requests.get", profile)
    monkeypatch.setattr("email_core.requests.post", lambda *a, **k: Reply(
        {"error": {"status": "PERMISSION_DENIED", "message": "Request had insufficient authentication scopes."}}, 403))
    missing_scope = client.post(route, json={"primaryEmail": "recipient@gmail.com",
                                           "gmailAccessToken": "short-lived-token"})
    assert missing_scope.status_code == 400
    assert "Gmail send permission was not granted" in missing_scope.json["error"]
