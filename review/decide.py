"""Human approval CLI; creates an immutable decision object and status event."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from google.cloud import pubsub_v1, storage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bss_core import approve_result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--status-topic", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--approver", required=True)
    parser.add_argument("--decision", required=True, choices=["approve", "reject"])
    args = parser.parse_args()

    key = hashlib.sha256(args.request_id.encode("utf-8")).hexdigest()
    bucket = storage.Client(project=args.project).bucket(args.bucket)
    original = json.loads(bucket.blob(f"results/{key}.json").download_as_text())
    decision = approve_result(original, args.approver, args.decision)
    object_name = f"decisions/{key}.json"
    bucket.blob(object_name).upload_from_string(
        json.dumps(decision), content_type="application/json", if_generation_match=0
    )
    event = {"requestId": args.request_id, "status": decision["status"],
             "resultUri": f"gs://{args.bucket}/{object_name}"}
    pubsub_v1.PublisherClient().publish(args.status_topic, json.dumps(event).encode("utf-8")).result(timeout=30)
    print(json.dumps(event))


if __name__ == "__main__":
    main()
