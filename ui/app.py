"""Catalogue, CPQ and order POC, locally or on private Cloud Run."""
from __future__ import annotations

import copy
import io
import json
import hashlib
import os
import sys
import uuid
from datetime import datetime, timezone
from threading import Lock
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from catalogue_core import DEFAULT_CATALOGUE, ValidationError, build_result, transition_offering, validate_catalogue, validate_request
from business_rules import RuleError, load_rules, validate_rules
from cpq_core import available_terms, configure_quote, load_policy
from customer_core import CustomerError, load_customers, validate_customer
from contract_core import contract_pdf
from email_core import DeliveryError, send_contract
from order_core import contract_review, create_order, next_mobile_order_id, product_order_payload
from state_store import read_json, write_json
from catalogue_assistant import (apply_patch as apply_assistant_patch, available_specifications,
                                 checked_state as checked_assistant_state, create_draft as create_assistant_draft,
                                 draft_preview, extract_patch as extract_assistant_patch,
                                 initial_state as initial_assistant_state, next_step as assistant_next_step,
                                 transcribe_audio)

HERE = Path(__file__).resolve().parent
DRAFT = HERE / "draft.json"
CATALOGUE_LOCK = Lock()
RULE_DRAFT = HERE / "rules.json"
RULE_LOCK = Lock()
CUSTOMER_DRAFT = HERE / "customers.json"
CUSTOMER_LOCK = Lock()
QUOTE_DRAFT = HERE / "quotes.json"
ORDER_DRAFT = HERE / "orders.json"
ORDER_LOCK = Lock()
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024


def current_catalogue():
    return read_json(DRAFT, None) or copy.deepcopy(DEFAULT_CATALOGUE)


def current_rules():
    stored = read_json(RULE_DRAFT, None)
    return validate_rules(stored) if stored is not None else load_rules()


def current_customers():
    return read_json(CUSTOMER_DRAFT, None) or load_customers()


def _read_store(path):
    return read_json(path, {})


def _write_store(path, value):
    write_json(path, value)


def _quote_record(quote_id):
    record = _read_store(QUOTE_DRAFT).get(quote_id)
    if record is None:
        raise ValidationError("Validated quote not found")
    if record["result"]["status"] != "VALIDATED":
        raise ValidationError("Quote needs human approval before order submission")
    if (record["catalogue"] != current_catalogue() or record["rules"] != current_rules()
            or record["policy"] != load_policy()):
        raise ValidationError("Catalogue or pricing policy changed; validate the quote again")
    return record


def commercial_view(catalogue):
    """Keep service designs and network targets off the product manager API."""
    view = copy.deepcopy(catalogue)
    view.pop("serviceSpecifications", None)
    for spec in view["productSpecifications"]:
        spec.pop("serviceSpecificationIds", None)
    return view


@app.get("/")
def index():
    return send_from_directory(HERE, "index.html")


@app.get("/healthz")
def health():
    return jsonify(status="ok")


@app.post("/api/agent/requests")
def submit_agent_request():
    topic = os.environ.get("REQUESTS_TOPIC")
    if not topic:
        return jsonify(error="Cloud agent is not configured"), 503
    try:
        body = request.get_json(force=True)
        if not isinstance(body, dict):
            raise ValidationError("Customer request must be an object")
        customer_request = {
            "requestId": "web-" + uuid.uuid4().hex,
            "customerId": str(body.get("customerId", "")),
            "segment": body.get("segment", "consumer"),
            "text": body.get("text", ""),
            "context": body.get("context", {}),
        }
        validate_request(customer_request)
        from google.cloud import pubsub_v1

        pubsub_v1.PublisherClient().publish(topic, json.dumps(customer_request).encode("utf-8")).result(timeout=30)
        return jsonify(requestId=customer_request["requestId"], status="PROCESSING"), 202
    except (ValidationError, ValueError, TypeError) as exc:
        return jsonify(error=str(exc)), 400


@app.get("/api/agent/results/<request_id>")
def agent_result(request_id):
    bucket_name = os.environ.get("RESULT_BUCKET")
    if not bucket_name or not request_id.startswith("web-") or len(request_id) != 36:
        return jsonify(error="Result not found"), 404
    from google.api_core.exceptions import NotFound
    from google.cloud import storage

    key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
    blob = storage.Client().bucket(bucket_name).blob(f"results/{key}.json")
    try:
        result = json.loads(blob.download_as_text())
    except NotFound:
        return jsonify(requestId=request_id, status="PROCESSING"), 202
    return jsonify(result)


@app.get("/<path:name>")
def static_file(name):
    if name not in ("app.js", "rules.js", "cpq.js", "assistant.js", "style.css", "assistant.css"):
        return jsonify(error="not found"), 404
    return send_from_directory(HERE, name)


@app.get("/api/rules")
def get_rules():
    return jsonify(current_rules())


@app.get("/api/customers")
def get_customers():
    return jsonify(current_customers())


@app.post("/api/customers")
def create_customer():
    try:
        body = request.get_json(force=True)
        if not isinstance(body, dict):
            raise CustomerError("Customer must be an object")
        candidate = validate_customer({**body, "id": "customer-" + uuid.uuid4().hex[:12]})
        with CUSTOMER_LOCK:
            store = current_customers()
            if any(row["email"].lower() == candidate["email"].lower() for row in store["customers"]):
                raise CustomerError("A customer with this email already exists")
            store["customers"].append(candidate)
            store["version"] = str(uuid.uuid4())
            _write_store(CUSTOMER_DRAFT, store)
        return jsonify(candidate), 201
    except (CustomerError, ValueError, TypeError) as exc:
        return jsonify(error=str(exc)), 400


@app.get("/api/cpq/options")
def cpq_options():
    policy = load_policy()
    catalogue = current_catalogue()
    specifications = {row["id"]: row for row in catalogue["productSpecifications"]}
    add_ons = {row["offeringId"] for row in policy["productConstraints"] if row["kind"] == "requiresAny"}
    offers = [{"id": offer["id"], "name": offer["name"], "monthlyPrice": offer["monthlyPrice"],
               "terms": available_terms(policy, offer["id"]),
               "termPrices": {str(row["months"]): row["monthlyPrice"] for row in policy["termPrices"] if row["offeringId"] == offer["id"]},
               "kind": "addOn" if offer["id"] in add_ons else "plan",
               "allowances": [{"name": specifications[ref["id"]]["name"], "value": ref["value"], "unit": specifications[ref["id"]]["unit"],
                               "characteristic": specifications[ref["id"]]["characteristic"]}
                              for ref in specifications[offer["productSpecification"]["id"]]["bundledProductSpecification"]]}
              for offer in catalogue["productOfferings"] if offer["lifecycleStatus"] == "Active"]
    return jsonify({"customer": load_customers()["customers"][0], "offers": offers, "promotions": policy["promotions"], "policyVersion": policy["version"]})


@app.post("/api/cpq/quote")
def cpq_quote():
    try:
        body = request.get_json(force=True)
        if not isinstance(body, dict):
            raise ValidationError("CPQ request must be an object")
        customer = next((row for row in load_customers()["customers"] + current_customers()["customers"] if row["id"] == body.get("customerId")), None)
        if customer is None:
            raise ValidationError("Select a saved customer")
        catalogue, rules, policy = current_catalogue(), current_rules(), load_policy()
        result = configure_quote(customer, body.get("selections"), body.get("promotionId"),
                                 catalogue=catalogue, rules=rules, policy=policy)
        with ORDER_LOCK:
            quotes = _read_store(QUOTE_DRAFT)
            quotes[result["quote"]["id"]] = {"result": result, "customer": customer,
                                               "catalogue": catalogue, "rules": rules, "policy": policy}
            _write_store(QUOTE_DRAFT, quotes)
        return jsonify(result)
    except (ValidationError, CustomerError, RuleError, ValueError, TypeError) as exc:
        return jsonify(error=str(exc)), 400


@app.get("/api/cpq/quotes/<quote_id>/order-payload")
def prepare_product_order(quote_id):
    try:
        record = _quote_record(quote_id)
        return jsonify({"productOrder": product_order_payload(record["result"], record["customer"], record["catalogue"]),
                        "contractReview": contract_review()})
    except (ValidationError, RuleError) as exc:
        return jsonify(error=str(exc)), 400


@app.post("/tmf-api/productOrderingManagement/v5/productOrder")
def submit_product_order():
    try:
        body = request.get_json(force=True)
        if not isinstance(body, dict) or not isinstance(body.get("quote"), list) or len(body["quote"]) != 1:
            raise ValidationError("TMF622 order request needs one validated quote reference")
        quote_id = body["quote"][0].get("id") if isinstance(body["quote"][0], dict) else None
        with ORDER_LOCK:
            orders = _read_store(ORDER_DRAFT)
            existing = next((row for row in orders.values() if row["quote"]["id"] == quote_id), None)
            if existing:
                if body != existing["requestPayload"]:
                    raise ValidationError("Order differs from the previously submitted quote")
                return jsonify(existing["productOrder"]), 200
            record = _quote_record(quote_id)
            expected = product_order_payload(record["result"], record["customer"], record["catalogue"])
            if body != expected:
                raise ValidationError("Order differs from the validated quote; prepare it again")
            created_at = datetime.now(timezone.utc)
            order_id = next_mobile_order_id(orders, created_at)
            created = create_order(record["result"], record["customer"], record["catalogue"],
                                   order_id=order_id, created_at=created_at)
            created["requestPayload"] = expected
            orders[order_id] = created
            _write_store(ORDER_DRAFT, orders)
        return jsonify(created["productOrder"]), 201, {"Location": created["productOrder"]["href"]}
    except (ValidationError, RuleError, ValueError, TypeError) as exc:
        return jsonify(error=str(exc)), 400


@app.get("/tmf-api/productOrderingManagement/v5/productOrder/<order_id>")
def get_product_order(order_id):
    record = _read_store(ORDER_DRAFT).get(order_id)
    return (jsonify(record["productOrder"]), 200) if record else (jsonify(error="Order not found"), 404)


@app.get("/api/cpq/orders/<order_id>")
def get_order_details(order_id):
    record = _read_store(ORDER_DRAFT).get(order_id)
    return (jsonify(record), 200) if record else (jsonify(error="Order not found"), 404)


@app.get("/api/cpq/orders/<order_id>/contract.pdf")
def download_contract(order_id):
    record = _read_store(ORDER_DRAFT).get(order_id)
    if not record:
        return jsonify(error="Order not found"), 404
    return send_file(io.BytesIO(contract_pdf(record)), mimetype="application/pdf", as_attachment=True,
                     download_name=f"draft-contract-{order_id}.pdf")


@app.post("/api/cpq/orders/<order_id>/email")
def email_contract(order_id):
    record = _read_store(ORDER_DRAFT).get(order_id)
    if not record:
        return jsonify(error="Order not found"), 404
    try:
        body = request.get_json(force=True)
        if not isinstance(body, dict):
            raise DeliveryError("Email request must be an object")
        receipt = send_contract(record, body.get("primaryEmail"), body.get("copyEmail") or None,
                                body.get("gmailAccessToken"))
        return jsonify(status="sent", **receipt)
    except DeliveryError as exc:
        return jsonify(error=str(exc)), 400


@app.get("/api/email/config")
def email_configuration():
    provider = os.environ.get("MAIL_PROVIDER", "smtp").lower()
    return jsonify(provider=provider, clientId=os.environ.get("GMAIL_OAUTH_CLIENT_ID", "") if provider == "gmail" else "",
                   sender=os.environ.get("GMAIL_SENDER_EMAIL", "") if provider == "gmail" else "",
                   configured=bool(os.environ.get("GMAIL_OAUTH_CLIENT_ID")) if provider == "gmail"
                   else bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_FROM")))


@app.put("/api/rules")
def save_rules():
    try:
        candidate = request.get_json(force=True)
        validate_rules(candidate)
        with RULE_LOCK:
            if candidate["version"] != current_rules()["version"]:
                return jsonify(error="Rules changed since this page loaded. Reload before editing."), 409
            candidate["version"] = str(uuid.uuid4())
            _write_store(RULE_DRAFT, candidate)
        return jsonify(candidate)
    except (RuleError, ValueError, TypeError) as exc:
        return jsonify(error=str(exc)), 400


@app.get("/api/catalogue")
def get_catalogue():
    return jsonify(commercial_view(current_catalogue()))


@app.get("/api/catalogue/assistant/start")
def start_catalogue_assistant():
    catalogue = current_catalogue()
    specs = available_specifications(catalogue)
    if not specs:
        return jsonify(error="No service-backed product specifications are available"), 503
    state = initial_assistant_state(catalogue)
    return jsonify(state=state, step=assistant_next_step(state, catalogue), specifications=specs)


@app.post("/api/catalogue/assistant/transcribe")
def transcribe_catalogue_answer():
    try:
        recording = request.files.get("audio")
        if recording is None:
            raise ValidationError("Record an answer before transcribing it")
        mime_type = (recording.mimetype or "").lower()
        if mime_type not in {"audio/webm", "audio/ogg", "audio/mp4", "audio/wav"}:
            raise ValidationError("This browser's audio format is not supported")
        audio = recording.read(2 * 1024 * 1024 + 1)
        if not audio or len(audio) > 2 * 1024 * 1024:
            raise ValidationError("Record a short answer of up to 2 MB")
        return jsonify(transcript=transcribe_audio(audio, mime_type))
    except ValidationError as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        app.logger.exception("Catalogue assistant transcription failed")
        return jsonify(error="Gemini could not transcribe the recording. Please try again or type your answer."), 502


@app.post("/api/catalogue/assistant/turn")
def catalogue_assistant_turn():
    try:
        body = request.get_json(force=True)
        if not isinstance(body, dict) or not isinstance(body.get("message"), str) or not body["message"].strip() or len(body["message"]) > 2000:
            raise ValidationError("Enter a product description or answer of up to 2,000 characters")
        catalogue = current_catalogue()
        state = checked_assistant_state(body.get("state"), catalogue)
        step = assistant_next_step(state, catalogue)
        proposal = extract_assistant_patch(body["message"], state, step, catalogue)
        updated = apply_assistant_patch(state, proposal, catalogue)
        next_question = assistant_next_step(updated, catalogue)
        return jsonify(state=updated, step=next_question, ready=next_question["kind"] == "review",
                       preview=draft_preview(updated, catalogue))
    except ValidationError as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        app.logger.exception("Catalogue assistant model request failed")
        return jsonify(error="Gemini could not read that answer. Please try again."), 502


@app.post("/api/catalogue/assistant/draft")
def save_catalogue_assistant_draft():
    try:
        body = request.get_json(force=True)
        if not isinstance(body, dict):
            raise ValidationError("Product draft request must be an object")
        with CATALOGUE_LOCK:
            candidate, offering_id = create_assistant_draft(body.get("state"), current_catalogue())
            candidate["version"] = str(uuid.uuid4())
            _write_store(DRAFT, candidate)
        return jsonify(offeringId=offering_id, catalogue=commercial_view(candidate)), 201
    except ValidationError as exc:
        return jsonify(error=str(exc)), 400


@app.put("/api/catalogue")
def save_catalogue():
    try:
        candidate = request.get_json(force=True)
        with CATALOGUE_LOCK:
            current = current_catalogue()
            if not isinstance(candidate, dict) or candidate.get("version") != current["version"]:
                return jsonify(error="Catalogue changed since this page loaded. Reload before editing."), 409
            existing = {row["id"]: row["lifecycleStatus"] for row in current["productOfferings"]}
            candidate_ids = {row.get("id") for row in candidate.get("productOfferings", []) if isinstance(row, dict)}
            if any(status != "Draft" and oid not in candidate_ids for oid, status in existing.items()):
                raise ValidationError("Published or retired offerings cannot be deleted from the catalogue")
            for offer in candidate.get("productOfferings", []):
                expected = existing.get(offer.get("id"), "Draft")
                if offer.get("lifecycleStatus") != expected:
                    raise ValidationError("Use Publish or Retire for offering lifecycle changes; new offerings start as Draft")
            current_specs = {spec["id"]: spec for spec in current["productSpecifications"]}
            candidate["serviceSpecifications"] = current["serviceSpecifications"]
            for spec in candidate.get("productSpecifications", []):
                if spec.get("isBundle"):
                    continue
                old = current_specs.get(spec.get("id"))
                template = old or next((x for x in current_specs.values() if not x.get("isBundle") and x.get("characteristic") == spec.get("characteristic")), None)
                spec["serviceSpecificationIds"] = copy.deepcopy(template.get("serviceSpecificationIds", [])) if template else []
            validate_catalogue(candidate, allow_drafts=True)
            candidate["version"] = str(uuid.uuid4())
            _write_store(DRAFT, candidate)
            return jsonify(commercial_view(candidate))
    except (ValidationError, ValueError, TypeError) as exc:
        return jsonify(error=str(exc)), 400


@app.post("/api/catalogue/offerings/<offering_id>/<action>")
def offering_lifecycle(offering_id, action):
    try:
        body = request.get_json(force=True)
        with CATALOGUE_LOCK:
            catalogue = current_catalogue()
            if not isinstance(body, dict) or body.get("version") != catalogue["version"]:
                return jsonify(error="Catalogue changed since this page loaded. Reload before editing."), 409
            transition_offering(catalogue, offering_id, action)
            catalogue["version"] = str(uuid.uuid4())
            _write_store(DRAFT, catalogue)
            return jsonify(commercial_view(catalogue))
    except (ValidationError, ValueError, TypeError) as exc:
        return jsonify(error=str(exc)), 400


@app.post("/api/preview")
def preview_quote():
    try:
        body = request.get_json(force=True)
        if not isinstance(body, dict):
            raise ValidationError("Preview request must be an object")
        customer_request = {
            "requestId": "preview-" + uuid.uuid4().hex[:10],
            "customerId": str(body.get("customerId", "preview-customer")),
            "segment": body.get("segment", "consumer"),
            "text": body.get("text", ""),
            "context": body.get("context", {}),
        }
        validate_request(customer_request)
        proposal = {"productOfferingIds": [body.get("productOfferingId")], "discountPercent": body.get("discountPercent", 0),
                    "exceptionRequested": body.get("exceptionRequested", False)}
        result = build_result(customer_request, proposal, current_catalogue(), current_rules())
        return jsonify({"status": result["status"], "catalogueVersion": result["catalogueVersion"], "quote": result["quote"],
                        "rulesVersion": result["rulesVersion"], "ruleDecisions": result["ruleDecisions"], "approval": result["approval"]})
    except (ValidationError, ValueError, TypeError) as exc:
        return jsonify(error=str(exc)), 400


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8088, debug=False)
