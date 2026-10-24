"""Pub/Sub CloudEvent entry point for quote and order processing."""

import base64
import hashlib
import json
import logging
import os

import functions_framework
import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.cloud import pubsub_v1, storage
from google.api_core.exceptions import NotFound, PreconditionFailed
from opentelemetry import trace
from opentelemetry.propagate import inject
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

from bss_core import CATALOGUE, ValidationError, build_result, validate_request
from business_rules import load_rules, validate_rules


logging.basicConfig(level=logging.INFO)
PROJECT_ID = os.environ.get("PROJECT_ID", "")
REGION = os.environ.get("REGION", "europe-west2")
RESULT_BUCKET = os.environ.get("RESULT_BUCKET", "")
STATUS_TOPIC = os.environ.get("STATUS_TOPIC", "")
AGENT_RESOURCE = os.environ.get("AGENT_RESOURCE", "")
STATE_BUCKET = os.environ.get("STATE_BUCKET", "")

if PROJECT_ID:
    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter(project_id=PROJECT_ID)))
    trace.set_tracer_provider(provider)
TRACER = trace.get_tracer(__name__)


def current_configuration():
    catalogue, rules = CATALOGUE, load_rules()
    if STATE_BUCKET:
        bucket = storage.Client(project=PROJECT_ID).bucket(STATE_BUCKET)
        for name in ("draft.json", "rules.json"):
            blob = bucket.blob(f"state/{name}")
            try:
                value = json.loads(blob.download_as_text())
            except NotFound:
                continue
            if name == "draft.json":
                catalogue = value
            else:
                rules = validate_rules(value)
    return catalogue, rules


def call_agent(request: dict) -> dict:
    catalogue, _ = current_configuration()
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)
    url = f"https://{REGION}-aiplatform.googleapis.com/v1/{AGENT_RESOURCE}:query"
    headers = {"Content-Type": "application/json"}
    with TRACER.start_as_current_span("agent.query") as span:
        span.set_attribute("agent.resource", AGENT_RESOURCE)
        trace_context = {}
        inject(trace_context)
        response = session.post(url, json={
            "class_method": "query",
            "input": {"input": json.dumps({"request": request, "catalogue": catalogue, "traceContext": trace_context})}
        }, headers=headers, timeout=180)
        response.raise_for_status()
        payload = response.json()
        return payload.get("output", payload)


def process(request: dict) -> dict:
    validate_request(request)
    with TRACER.start_as_current_span("quote.process") as span:
        span.set_attribute("request.id", request["requestId"])
        catalogue, rules = current_configuration()
        proposal = call_agent(request)
        return build_result(request, proposal, catalogue, rules)


@functions_framework.cloud_event
def handle_request(cloud_event):
    try:
        raw = base64.b64decode(cloud_event.data["message"]["data"], validate=True)
        request = json.loads(raw)
    except (KeyError, ValueError, TypeError) as exc:
        logging.error("Discarding malformed Pub/Sub event: %s", exc)
        return
    request_id = request.get("requestId") if isinstance(request, dict) else None
    if not isinstance(request_id, str) or not request_id:
        request_id = f"invalid-{cloud_event['id']}"
    try:
        result = process(request)
    except ValidationError as exc:
        result = {"requestId": request_id, "status": "REJECTED", "error": str(exc)}

    key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
    object_name = f"results/{key}.json"
    bucket = storage.Client(project=PROJECT_ID).bucket(RESULT_BUCKET)
    blob = bucket.blob(object_name)
    try:
        blob.upload_from_string(json.dumps(result), content_type="application/json", if_generation_match=0)
    except PreconditionFailed:
        result = json.loads(blob.download_as_text())
    event = {"requestId": request_id, "status": result["status"], "resultUri": f"gs://{RESULT_BUCKET}/{object_name}"}
    pubsub_v1.PublisherClient().publish(STATUS_TOPIC, json.dumps(event).encode("utf-8")).result(timeout=30)
    logging.info("Processed request %s with status %s", request_id, result["status"])
