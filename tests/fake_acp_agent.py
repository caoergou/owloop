"""Scripted fake ACP agent for AcpAdapter tests — deterministic, no network.

Speaks just enough Agent Client Protocol (JSON-RPC 2.0 over stdio) to exercise
the client side: initialize, session/new, session/prompt, session/update
notifications, and a permission round-trip.

Scenario is selected by argv[1]:

- ``happy``      full turn: plan, tool_call, message chunks with a DONE
                 promise, usage_update, then ``stopReason: end_turn``.
- ``permission`` asks ``session/request_permission`` first and only completes
                 the turn if the client selects the ``allow_once`` option.
- ``refusal``    ends the turn with ``stopReason: refusal``.
- ``hang``       answers the handshake but never answers ``session/prompt``.
- ``crash``      exits 3 (after a stderr line) instead of answering the prompt.
"""

import json
import sys

SCENARIO = sys.argv[1] if len(sys.argv) > 1 else "happy"
SESSION_ID = "sess-fake-1"


def send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def notify(update: dict) -> None:
    send(
        {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {"sessionId": SESSION_ID, "update": update},
        }
    )


def finish_turn(prompt_id: int, stop_reason: str = "end_turn") -> None:
    if stop_reason == "end_turn":
        notify({"sessionUpdate": "plan", "entries": [{"content": "implement"}, {"content": "verify"}]})
        notify({"sessionUpdate": "tool_call", "toolCallId": "tc-1", "title": "pytest -q", "kind": "execute"})
        notify(
            {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "Implemented the spec.\nAll criteria pass.\n"},
            }
        )
        notify(
            {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "<promise>DONE</promise>"},
            }
        )
        notify(
            {
                "sessionUpdate": "usage_update",
                "used": 1234,
                "size": 200000,
                "cost": {"amount": 0.05, "currency": "USD"},
            }
        )
    else:
        notify(
            {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "I cannot continue with this request.\n"},
            }
        )
    send({"jsonrpc": "2.0", "id": prompt_id, "result": {"stopReason": stop_reason}})


def main() -> None:
    prompt_id: int | None = None

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)

        if "method" not in msg:
            # A response from the client — the only request we make is the
            # permission request (id 1).
            outcome = (msg.get("result") or {}).get("outcome") or {}
            assert prompt_id is not None
            if outcome.get("outcome") == "selected" and outcome.get("optionId") == "ok-once":
                finish_turn(prompt_id)
            else:
                finish_turn(prompt_id, stop_reason="refusal")
            continue

        method = msg["method"]
        if method == "initialize":
            params = msg.get("params") or {}
            assert params.get("protocolVersion") == 1
            send(
                {
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "result": {"protocolVersion": 1, "agentCapabilities": {}},
                }
            )
        elif method == "session/new":
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {"sessionId": SESSION_ID}})
        elif method == "session/prompt":
            prompt_id = msg["id"]
            if SCENARIO == "hang":
                continue
            if SCENARIO == "crash":
                print("fake agent: simulated crash", file=sys.stderr, flush=True)
                sys.exit(3)
            if SCENARIO == "permission":
                send(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "session/request_permission",
                        "params": {
                            "sessionId": SESSION_ID,
                            "toolCall": {"toolCallId": "tc-1", "title": "write src/app.py"},
                            "options": [
                                {"optionId": "no-always", "name": "Reject always", "kind": "reject_always"},
                                {"optionId": "ok-once", "name": "Allow once", "kind": "allow_once"},
                                {"optionId": "ok-always", "name": "Allow always", "kind": "allow_always"},
                            ],
                        },
                    }
                )
            elif SCENARIO == "refusal":
                finish_turn(prompt_id, stop_reason="refusal")
            else:
                finish_turn(prompt_id)


if __name__ == "__main__":
    main()
