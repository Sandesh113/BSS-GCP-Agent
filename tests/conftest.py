"""Keep every test away from the real local state files and cloud buckets."""

import pytest

from ui import app as ui


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    # Without this, tests that forget a monkeypatch write quotes into ui/quotes.json
    # or read a product manager's saved ui/draft.json and ui/rules.json.
    for name in ("STATE_BUCKET", "RESULT_BUCKET", "REQUESTS_TOPIC", "MAIL_PROVIDER",
                 "SMTP_HOST", "SMTP_FROM", "SMTP_USERNAME", "SMTP_PASSWORD", "GMAIL_OAUTH_CLIENT_ID"):
        monkeypatch.delenv(name, raising=False)
    state = tmp_path / "state"
    state.mkdir()
    for attr, filename in (("DRAFT", "draft.json"), ("RULE_DRAFT", "rules.json"),
                           ("CUSTOMER_DRAFT", "customers.json"), ("QUOTE_DRAFT", "quotes.json"),
                           ("ORDER_DRAFT", "orders.json")):
        monkeypatch.setattr(ui, attr, state / filename)
    return state
