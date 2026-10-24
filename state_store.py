"""Small JSON store for the demo UI; Cloud Storage is used on Cloud Run."""
from __future__ import annotations

import json
import os
from pathlib import Path


def _blob(path: Path):
    bucket_name = os.environ.get("STATE_BUCKET")
    if not bucket_name:
        return None
    from google.cloud import storage

    return storage.Client().bucket(bucket_name).blob(f"state/{path.name}")


def read_json(path: Path, default=None):
    blob = _blob(path)
    if blob is not None:
        from google.api_core.exceptions import NotFound

        try:
            return json.loads(blob.download_as_text())
        except NotFound:
            return default
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path: Path, value):
    payload = json.dumps(value, indent=2) + "\n"
    blob = _blob(path)
    if blob is not None:
        blob.upload_from_string(payload, content_type="application/json")
        return
    temp = path.with_suffix(".tmp")
    temp.write_text(payload, encoding="utf-8")
    temp.replace(path)
