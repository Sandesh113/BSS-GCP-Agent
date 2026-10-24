"""Stage the pickled agent and requirements in a pre-created GCS bucket."""

import argparse
import hashlib
import importlib
from pathlib import Path

import cloudpickle
from google.cloud import storage

from agent import root_agent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--revision-only", action="store_true", help="Print revision without uploading")
    args = parser.parse_args()
    base = Path(__file__).parent
    cloudpickle.register_pickle_by_value(importlib.import_module("agent"))
    pickled = cloudpickle.dumps(root_agent)
    requirements = (base / "requirements.txt").read_bytes()
    # Cloudpickle bytes can vary between processes; source and dependencies form a stable deployment revision.
    revision = hashlib.sha256((base / "agent.py").read_bytes() + requirements).hexdigest()
    prefix = f"agent/{revision}"
    print(f"AGENT_REVISION={revision}")
    if not args.revision_only:
        client = storage.Client(project=args.project)
        bucket = client.bucket(args.bucket)
        bucket.blob(f"{prefix}/agent.pkl").upload_from_string(pickled, content_type="application/octet-stream")
        bucket.blob(f"{prefix}/requirements.txt").upload_from_string(requirements, content_type="text/plain")
        print(f"Staged agent to gs://{args.bucket}/{prefix}/")


if __name__ == "__main__":
    main()
