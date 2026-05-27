from __future__ import annotations

from aipf.redaction import redact_data, redact_text

SECRET = "sk-test-secret-value"


def test_redact_text_redacts_exact_secret_and_known_shapes() -> None:
    text = (
        f"Authorization: Bearer {SECRET} "
        f"https://proxy.example.com/v1/models?api_key={SECRET} "
        f"AIPF_API_KEY={SECRET}"
    )

    redacted = redact_text(text, (SECRET,))

    assert SECRET not in redacted
    assert "Authorization: ***" in redacted
    assert "api_key=***" in redacted
    assert "AIPF_API_KEY=***" in redacted


def test_redact_data_recurses_and_redacts_sensitive_keys() -> None:
    payload = {
        "headers": {"Authorization": f"Bearer {SECRET}", "x-api-key": SECRET},
        "nested": [{"message": f"token={SECRET}"}],
        "safe": "visible",
    }

    redacted = redact_data(payload, (SECRET,))

    assert redacted["headers"]["Authorization"] == "***"
    assert redacted["headers"]["x-api-key"] == "***"
    assert redacted["nested"][0]["message"] == "token=***"
    assert redacted["safe"] == "visible"
