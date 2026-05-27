from __future__ import annotations

from aipf.scanning import compute_fingerprint, scan_phrases, scan_tool_ids, snippet


def test_scan_phrases_finds_case_insensitive() -> None:
    text = "Sure — I am Claude and my System Prompt says to be helpful."
    findings = scan_phrases(text)
    phrases = {f.phrase for f in findings}
    assert "you are claude" not in phrases  # not present
    assert "system prompt" in phrases
    finding = next(f for f in findings if f.phrase == "system prompt")
    assert "system prompt" in finding.context_snippet.lower()
    assert finding.position >= 0


def test_scan_phrases_empty() -> None:
    assert scan_phrases("") == []
    assert scan_phrases("clean text with no markers") == []


def test_compute_fingerprint_anthropic() -> None:
    text = "I aim to be helpful. I'd be happy to help with that. I don't have personal opinions."
    fp = compute_fingerprint(text)
    assert fp.verdict == "anthropic"
    assert fp.anthropic_score >= 2


def test_compute_fingerprint_openai() -> None:
    text = "Certainly! I can certainly help. Let me help with that. Sure, here is an example."
    fp = compute_fingerprint(text)
    assert fp.verdict == "openai"
    assert fp.openai_score >= 2


def test_compute_fingerprint_unknown() -> None:
    fp = compute_fingerprint("")
    assert fp.verdict == "unknown"


def test_scan_tool_ids_anthropic() -> None:
    text = "use toolu_01abc and toolu_xyz999 here"
    matches = scan_tool_ids(text)
    assert "anthropic" in matches
    assert "toolu_01abc" in matches["anthropic"]
    assert "toolu_xyz999" in matches["anthropic"]


def test_scan_tool_ids_openai() -> None:
    text = "function call_AbC123Def is invoked"
    matches = scan_tool_ids(text)
    assert "openai" in matches
    assert "call_AbC123Def" in matches["openai"]


def test_scan_tool_ids_none() -> None:
    assert scan_tool_ids("nothing here") == {}


def test_snippet_short_passthrough() -> None:
    assert snippet("hello") == "hello"


def test_snippet_truncates() -> None:
    long = "x" * 5000
    s = snippet(long, length=100)
    assert len(s) <= 101
    assert s.endswith("…")
