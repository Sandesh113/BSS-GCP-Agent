"""Guided product creation uses model extraction but code validates the saved offer."""

import io

from catalogue_assistant import apply_patch, initial_state, next_step
from catalogue_core import DEFAULT_CATALOGUE, ValidationError
from customer_core import load_customers
from ui import app as ui


def test_guided_answer_creates_draft_then_publishes_into_cpq(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "DRAFT", tmp_path / "catalogue.json")
    monkeypatch.setattr(ui, "QUOTE_DRAFT", tmp_path / "quotes.json")
    client = ui.app.test_client()
    started = client.get("/api/catalogue/assistant/start")
    assert started.status_code == 200
    assert [row["id"] for row in started.json["specifications"]] == ["ps-voice", "ps-data", "ps-sms"]
    assert started.json["step"]["kind"] == "name"

    monkeypatch.setattr(ui, "extract_assistant_patch", lambda *args: {
        "name": "Guided Mini", "allowances": {
            "ps-voice": {"include": True, "value": 100},
            "ps-data": {"include": True, "value": 2},
            "ps-sms": {"include": False}},
        "monthlyPrice": "11.00", "setupPrice": "0", "segments": ["consumer"]})
    turn = client.post("/api/catalogue/assistant/turn", json={
        "state": started.json["state"],
        "message": "I want Guided Mini with 100 voice minutes and two gigabytes, no texts, £11 a month, no setup, for consumers."})
    assert turn.status_code == 200, turn.json
    assert turn.json["ready"] is True
    assert turn.json["preview"]["monthlyPrice"] == "11.00"
    saved = client.post("/api/catalogue/assistant/draft", json={"state": turn.json["state"]})
    assert saved.status_code == 201, saved.json
    offer_id = saved.json["offeringId"]
    assert next(row for row in saved.json["catalogue"]["productOfferings"] if row["id"] == offer_id)["lifecycleStatus"] == "Draft"
    assert all(row["id"] != offer_id for row in client.get("/api/cpq/options").json["offers"])
    published = client.post(f"/api/catalogue/offerings/{offer_id}/publish",
                            json={"version": saved.json["catalogue"]["version"]})
    assert published.status_code == 200, published.json
    assert any(row["id"] == offer_id for row in client.get("/api/cpq/options").json["offers"])
    quote = client.post("/api/cpq/quote", json={
        "customerId": load_customers()["customers"][0]["id"],
        "selections": [{"offeringId": offer_id, "termMonths": 12}]})
    assert quote.status_code == 200 and quote.json["status"] == "VALIDATED"


def test_guided_questions_follow_missing_and_partial_allowances():
    state = initial_state(DEFAULT_CATALOGUE)
    state = apply_patch(state, {"name": "Progressive"}, DEFAULT_CATALOGUE)
    assert next_step(state, DEFAULT_CATALOGUE)["specificationId"] == "ps-voice"
    state = apply_patch(state, {"allowances": {"ps-voice": {"include": True}}}, DEFAULT_CATALOGUE)
    assert next_step(state, DEFAULT_CATALOGUE)["kind"] == "allowance"
    state = apply_patch(state, {"allowances": {"ps-voice": {"include": True, "value": 150}}}, DEFAULT_CATALOGUE)
    assert next_step(state, DEFAULT_CATALOGUE)["specificationId"] == "ps-data"


def test_model_cannot_invent_specification_or_invalid_allowance():
    state = initial_state(DEFAULT_CATALOGUE)
    for proposal in ({"allowances": {"ps-roaming": {"include": True, "value": 1}}},
                     {"allowances": {"ps-data": {"include": True, "value": -1}}},
                     {"allowances": {"ps-data": {"include": True, "value": 0}}}):
        try:
            apply_patch(state, proposal, DEFAULT_CATALOGUE)
        except ValidationError:
            pass
        else:
            raise AssertionError("Invalid model proposal was accepted")


def test_guided_draft_rejects_incomplete_or_stale_state(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "DRAFT", tmp_path / "catalogue.json")
    client = ui.app.test_client()
    state = client.get("/api/catalogue/assistant/start").json["state"]
    assert client.post("/api/catalogue/assistant/draft", json={"state": state}).status_code == 400
    state["catalogueVersion"] = "outdated"
    assert client.post("/api/catalogue/assistant/draft", json={"state": state}).status_code == 400


def test_voice_recording_is_validated_and_returns_editable_transcript(monkeypatch):
    monkeypatch.setattr(ui, "transcribe_audio", lambda audio, mime: f"{mime}: {len(audio)} bytes")
    client = ui.app.test_client()
    response = client.post("/api/catalogue/assistant/transcribe", data={
        "audio": (io.BytesIO(b"recorded voice"), "answer.webm", "audio/webm")})
    assert response.status_code == 200
    assert response.json["transcript"] == "audio/webm: 14 bytes"
    assert client.post("/api/catalogue/assistant/transcribe", data={}).status_code == 400
    assert client.post("/api/catalogue/assistant/transcribe", data={
        "audio": (io.BytesIO(b"not audio"), "answer.txt", "text/plain")}).status_code == 400
    assert client.post("/api/catalogue/assistant/transcribe", data={
        "audio": (io.BytesIO(b""), "answer.webm", "audio/webm")}).status_code == 400
    assert client.post("/api/catalogue/assistant/transcribe", data={
        "audio": (io.BytesIO(b"x" * (2 * 1024 * 1024 + 1)), "answer.webm", "audio/webm")}).status_code == 400
