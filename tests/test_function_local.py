"""CloudEvent boundary exercised locally with in-memory cloud clients."""

import base64
import json

from function import main as fn


class FakeBlob:
    def __init__(self, objects, name):
        self.objects = objects
        self.name = name

    def upload_from_string(self, body, **kwargs):
        if self.name in self.objects:
            raise fn.PreconditionFailed("result already exists")
        self.objects[self.name] = json.loads(body)

    def download_as_text(self):
        return json.dumps(self.objects[self.name])


class FakeBucket:
    def __init__(self, objects):
        self.objects = objects

    def blob(self, name):
        return FakeBlob(self.objects, name)


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def bucket(self, name):
        return FakeBucket(self.objects)


class FakePublishResult:
    def result(self, timeout):
        return "published"


class FakePublisher:
    def __init__(self, events):
        self.events = events

    def publish(self, topic, body):
        self.events.append((topic, json.loads(body)))
        return FakePublishResult()


class FakeEvent:
    def __init__(self, payload):
        self.data = {"message": {"data": base64.b64encode(json.dumps(payload).encode()).decode()}}

    def __getitem__(self, key):
        return "event-test"


def test_cloud_event_persists_decomposed_result_and_emits_status(monkeypatch):
    storage = FakeStorage()
    events = []
    monkeypatch.setattr(fn.storage, "Client", lambda **kwargs: storage)
    monkeypatch.setattr(fn.pubsub_v1, "PublisherClient", lambda: FakePublisher(events))
    monkeypatch.setattr(fn, "RESULT_BUCKET", "test-results")
    monkeypatch.setattr(fn, "STATUS_TOPIC", "test-status")
    monkeypatch.setattr(fn, "call_agent", lambda request: {"productOfferingIds": ["po-mobile-mini"]})
    fn.handle_request(FakeEvent({"requestId": "cloud-local-mini", "customerId": "customer-1",
                                 "segment": "consumer", "text": "Mobile Mini"}))
    assert len(storage.objects) == len(events) == 1
    result = next(iter(storage.objects.values()))
    assert result["status"] == "VALIDATED"
    assert [item["service"]["serviceSpecification"]["id"] for item in result["serviceOrder"]["orderItem"]] == [
        "cfs-voice", "cfs-data", "cfs-sms"]
    assert events[0][1]["status"] == "VALIDATED"
    assert events[0][1]["resultUri"].startswith("gs://test-results/results/")


def test_cloud_event_rejects_invalid_request_before_agent_call(monkeypatch):
    storage = FakeStorage()
    events = []
    monkeypatch.setattr(fn.storage, "Client", lambda **kwargs: storage)
    monkeypatch.setattr(fn.pubsub_v1, "PublisherClient", lambda: FakePublisher(events))
    monkeypatch.setattr(fn, "call_agent", lambda request: (_ for _ in ()).throw(AssertionError("agent called")))
    fn.handle_request(FakeEvent({"requestId": "cloud-invalid", "customerId": "customer-1",
                                 "segment": "consumer", "text": ""}))
    assert next(iter(storage.objects.values()))["status"] == "REJECTED"
    assert events[0][1]["status"] == "REJECTED"


def test_duplicate_pubsub_delivery_keeps_first_result(monkeypatch):
    storage = FakeStorage()
    events = []
    monkeypatch.setattr(fn.storage, "Client", lambda **kwargs: storage)
    monkeypatch.setattr(fn.pubsub_v1, "PublisherClient", lambda: FakePublisher(events))
    proposals = iter([{"productOfferingIds": ["po-mobile-mini"]},
                      {"productOfferingIds": ["po-mobile-plus"]}])
    monkeypatch.setattr(fn, "call_agent", lambda request: next(proposals))
    event = FakeEvent({"requestId": "cloud-duplicate", "customerId": "customer-1",
                       "segment": "consumer", "text": "Mobile Mini"})
    fn.handle_request(event)
    fn.handle_request(event)
    assert len(storage.objects) == 1
    assert next(iter(storage.objects.values()))["quote"]["quoteItem"][0]["productOffering"]["id"] == "po-mobile-mini"
    assert len(events) == 2 and events[0][1]["resultUri"] == events[1][1]["resultUri"]
