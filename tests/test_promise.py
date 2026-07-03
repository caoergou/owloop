"""Tests for the <promise> signal parser."""

from __future__ import annotations

from owloop.promise import parse_promise_signal


def test_parse_done_signal() -> None:
    assert parse_promise_signal("ok\n<promise>DONE</promise>") == ("DONE", "")


def test_parse_blocked_signal_with_payload() -> None:
    assert parse_promise_signal("<promise>BLOCKED:missing env var</promise>") == (
        "BLOCKED",
        "missing env var",
    )


def test_parse_decide_signal_with_payload() -> None:
    assert parse_promise_signal("<promise>DECIDE:which API to use?</promise>") == (
        "DECIDE",
        "which API to use?",
    )


def test_parse_no_signal() -> None:
    assert parse_promise_signal("just some output") is None


def test_parse_malformed_signal() -> None:
    assert parse_promise_signal("<promise>UNKNOWN:thing</promise>") is None


def test_parse_blocked_without_payload() -> None:
    assert parse_promise_signal("<promise>BLOCKED</promise>") == ("BLOCKED", "")


def test_parse_payload_is_stripped() -> None:
    assert parse_promise_signal("<promise>BLOCKED:  extra spaces  </promise>") == (
        "BLOCKED",
        "extra spaces",
    )


def test_parse_returns_first_signal() -> None:
    text = "<promise>BLOCKED:first</promise>\n<promise>DONE</promise>"
    assert parse_promise_signal(text) == ("BLOCKED", "first")
