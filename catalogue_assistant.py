"""Guided natural-language authoring of a service-backed draft offering."""

from __future__ import annotations

import copy
import base64
import json
import math
import os
import uuid

from catalogue_core import ValidationError, money, validate_catalogue


def available_specifications(catalogue):
    """Product managers see the sellable building blocks, never CFS details."""
    return [{"id": row["id"], "name": row["name"], "unit": row["unit"]}
            for row in catalogue["productSpecifications"]
            if not row.get("isBundle") and row.get("serviceSpecificationIds")]


def initial_state(catalogue):
    return {"catalogueVersion": catalogue["version"], "name": "", "allowances": {},
            "monthlyPrice": None, "setupPrice": None, "segments": None}


def checked_state(raw, catalogue):
    if not isinstance(raw, dict) or raw.get("catalogueVersion") != catalogue["version"]:
        raise ValidationError("Catalogue changed. Restart product creation to use the latest building blocks.")
    state = initial_state(catalogue)
    name = raw.get("name", "")
    if not isinstance(name, str) or len(name) > 120:
        raise ValidationError("Product name is invalid")
    state["name"] = name.strip()
    specs = {row["id"] for row in available_specifications(catalogue)}
    allowances = raw.get("allowances", {})
    if not isinstance(allowances, dict) or any(key not in specs for key in allowances):
        raise ValidationError("Product contains an unknown specification")
    for key, choice in allowances.items():
        if not isinstance(choice, dict) or not isinstance(choice.get("include"), bool):
            raise ValidationError("Specification choice is invalid")
        if choice["include"]:
            value = choice.get("value")
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) or value <= 0 or value > 1000000):
                raise ValidationError("Allowance must be a positive number")
            state["allowances"][key] = {"include": True, "value": value}
        else:
            state["allowances"][key] = {"include": False, "value": None}
    for key in ("monthlyPrice", "setupPrice"):
        if raw.get(key) is not None:
            state[key] = money(raw[key])
    segments = raw.get("segments")
    if segments is not None:
        if (not isinstance(segments, list) or not segments or any(not isinstance(value, str) for value in segments)
                or len(set(segments)) != len(segments) or any(value not in ("consumer", "business") for value in segments)):
            raise ValidationError("Customer segment must be consumer, business or both")
        state["segments"] = segments
    return state


def next_step(state, catalogue):
    if not state["name"]:
        return {"kind": "name", "question": "What would you like to call this product? You can also describe its allowances and price in one answer."}
    for spec in available_specifications(catalogue):
        choice = state["allowances"].get(spec["id"])
        if choice is None:
            return {"kind": "specification", "specificationId": spec["id"],
                    "question": f"Do you want {spec['name']}? If yes, how many {spec['unit']} should it include?"}
        if choice["include"] and choice["value"] is None:
            return {"kind": "allowance", "specificationId": spec["id"],
                    "question": f"How many {spec['unit']} of {spec['name']} should this product include?"}
    if not any(choice["include"] for choice in state["allowances"].values()):
        return {"kind": "chooseOne", "question": "Select at least one allowance. Which of the listed product specifications should this offer include?"}
    if state["monthlyPrice"] is None:
        return {"kind": "monthlyPrice", "question": "What should the monthly price be in pounds?"}
    if state["setupPrice"] is None:
        return {"kind": "setupPrice", "question": "Is there a one-time setup charge? Say zero if there is none."}
    if state["segments"] is None:
        return {"kind": "segments", "question": "Is this offer for consumers, businesses or both?"}
    return {"kind": "review", "question": "Review the proposed product. You can tell me what to change, or save it as a Draft."}


def extract_patch(message, state, step, catalogue):
    """Gemini extracts facts; it does not create catalogue records or set prices."""
    import google.auth
    from google.auth.transport.requests import Request
    import requests

    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT_ID")
    if not project:
        raise RuntimeError("Catalogue assistant model is not configured")
    region = os.environ.get("MODEL_REGION", "eu")
    model = os.environ.get("MODEL_NAME", "gemini-3.5-flash")
    endpoint = os.environ.get("MODEL_API_ENDPOINT", "https://aiplatform.eu.rep.googleapis.com").rstrip("/")
    specs = available_specifications(catalogue)
    instruction = (
        "Extract only facts explicitly stated in the latest product manager message. "
        "Return one JSON object with optional fields: name (string), allowances (object keyed by allowed specification ID "
        "with {include:boolean,value:number|null}), monthlyPrice (GBP numeric string), setupPrice (GBP numeric string), "
        "segments (array containing consumer and/or business). Omit unstated fields. "
        "A plain yes/no or amount answers the current question. Map words and spoken numbers to numeric allowances. "
        "'No setup fee' is zero. Do not invent prices, offerings, IDs, or service mappings. "
        "The previous state is context for corrections, not evidence for output. Return JSON only."
    )
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(Request())
    payload = {"systemInstruction": {"parts": [{"text": instruction}]},
               "contents": [{"role": "user", "parts": [{"text": json.dumps({
                   "latestMessage": message, "currentQuestion": step, "currentState": state,
                   "allowedSpecifications": specs})}]}],
               "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
    url = f"{endpoint}/v1/projects/{project}/locations/{region}/publishers/google/models/{model}:generateContent"
    response = requests.post(url, headers={"Authorization": f"Bearer {credentials.token}",
                                          "Content-Type": "application/json"}, json=payload, timeout=60)
    response.raise_for_status()
    parts = response.json()["candidates"][0]["content"]["parts"]
    proposal = json.loads("".join(part.get("text", "") for part in parts))
    if not isinstance(proposal, dict):
        raise ValueError("Model returned an invalid product proposal")
    return proposal


def transcribe_audio(audio, mime_type):
    """Transcribe a short recording without storing it or changing catalogue state."""
    import google.auth
    from google.auth.transport.requests import Request
    import requests

    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT_ID")
    if not project:
        raise RuntimeError("Catalogue assistant model is not configured")
    region = os.environ.get("MODEL_REGION", "eu")
    model = os.environ.get("MODEL_NAME", "gemini-3.5-flash")
    endpoint = os.environ.get("MODEL_API_ENDPOINT", "https://aiplatform.eu.rep.googleapis.com").rstrip("/")
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(Request())
    payload = {"contents": [{"role": "user", "parts": [
        {"text": "Transcribe the spoken English in this short recording. Return only the words spoken, "
                 "without commentary or quotation marks. Do not invent words. If there is no intelligible speech, "
                 "return exactly NO_SPEECH."},
        {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(audio).decode("ascii")}},
    ]}], "generationConfig": {"temperature": 0, "maxOutputTokens": 1024}}
    url = f"{endpoint}/v1/projects/{project}/locations/{region}/publishers/google/models/{model}:generateContent"
    response = requests.post(url, headers={"Authorization": f"Bearer {credentials.token}",
                                           "Content-Type": "application/json"}, json=payload, timeout=60)
    response.raise_for_status()
    parts = response.json()["candidates"][0]["content"]["parts"]
    transcript = "".join(part.get("text", "") for part in parts).strip().strip('"')
    if not transcript or transcript.upper() == "NO_SPEECH":
        raise ValidationError("No clear speech was detected. Please try again or type your answer.")
    if len(transcript) > 2000:
        raise ValidationError("The recording is too long. Please speak a shorter answer or type it.")
    return transcript


def apply_patch(state, patch, catalogue):
    if not isinstance(patch, dict):
        raise ValidationError("Could not read that answer")
    updated = copy.deepcopy(state)
    if "name" in patch:
        updated["name"] = patch["name"]
    specs = {row["id"] for row in available_specifications(catalogue)}
    selections = patch.get("allowances", {})
    if not isinstance(selections, dict):
        raise ValidationError("Could not read the specification choices")
    for key, choice in selections.items():
        if key not in specs:
            raise ValidationError("The answer referenced an unsupported specification")
        if not isinstance(choice, dict) or not isinstance(choice.get("include"), bool):
            raise ValidationError("Could not read that specification choice")
        updated["allowances"][key] = {"include": choice["include"],
                                       "value": choice.get("value") if choice["include"] else None}
    for key in ("monthlyPrice", "setupPrice", "segments"):
        if key in patch:
            updated[key] = patch[key]
    return checked_state(updated, catalogue)


def draft_preview(state, catalogue):
    choices = {row["id"]: row for row in available_specifications(catalogue)}
    return {"name": state["name"], "allowances": [
        {"name": choices[key]["name"], "value": choice["value"], "unit": choices[key]["unit"]}
        for key, choice in state["allowances"].items() if choice["include"]],
        "monthlyPrice": state["monthlyPrice"], "setupPrice": state["setupPrice"],
        "segments": state["segments"]}


def create_draft(state, catalogue):
    state = checked_state(state, catalogue)
    if next_step(state, catalogue)["kind"] != "review":
        raise ValidationError("Answer the remaining product questions before saving")
    candidate = copy.deepcopy(catalogue)
    suffix = uuid.uuid4().hex[:12]
    spec_id, offer_id = f"ps-guided-{suffix}", f"po-guided-{suffix}"
    candidate["productSpecifications"].append({
        "id": spec_id, "name": state["name"] + " specification", "isBundle": True,
        "bundledProductSpecification": [{"id": key, "value": choice["value"]}
                                        for key, choice in state["allowances"].items() if choice["include"]]})
    candidate["productOfferings"].append({
        "id": offer_id, "name": state["name"], "lifecycleStatus": "Draft",
        "monthlyPrice": state["monthlyPrice"], "setupPrice": state["setupPrice"],
        "allowedSegments": state["segments"], "productSpecification": {"id": spec_id}})
    validate_catalogue(candidate, allow_drafts=True)
    return candidate, offer_id
