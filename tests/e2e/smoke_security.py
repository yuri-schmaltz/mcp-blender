"""End-to-end smoke for the new transport hardening.

Run with a Blender instance started by ``headless_runner.py``. Connects,
exercises the socket server in three scenarios:

1. Round-trip without any auth: confirm basic calls still work.
2. Token gate: with ``BLENDER_MCP_TOKEN`` set in BOTH processes,
   the wrong token must be refused and the right token accepted.
3. Payload cap: with ``BLENDER_MCP_MAX_PAYLOAD_BYTES=2048`` set in
   the Blender process, a multi-MiB payload must be rejected.

Exits 0 on success, 1 on any check failure. Prints a small table at the
end summarising what was exercised.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time

PORT = int(os.environ.get("BLENDER_MCP_HARNESS_PORT", "9876"))
TOKEN = os.environ.get("BLENDER_MCP_TOKEN", "smoke-secret-32-chars-aaaaaaaaaaaa")[:64]
TOKEN_ENABLED = bool(os.environ.get("BLENDER_MCP_TOKEN"))


def _send(payload: dict, port: int = PORT, expect_close: bool = False) -> dict:
    """Send one JSON command, return the response. Tolerates short reads."""
    s = socket.create_connection(("127.0.0.1", port), timeout=10)
    s.sendall(json.dumps(payload).encode("utf-8"))
    chunks: list[bytes] = []
    s.settimeout(8 if not expect_close else 4)
    while True:
        try:
            c = s.recv(65536)
        except TimeoutError:
            break
        if not c:
            break
        chunks.append(c)
        try:
            return json.loads(b"".join(chunks))
        except json.JSONDecodeError:
            continue
    if chunks:
        try:
            return json.loads(b"".join(chunks))
        except json.JSONDecodeError:
            return {"_raw": b"".join(chunks).decode("utf-8", "replace")}
    return {}


def _send_buffered(raw: bytes, port: int = PORT) -> list[bytes]:
    """Send an oversized raw buffer; return what came back (chunks)."""
    s = socket.create_connection(("127.0.0.1", port), timeout=10)
    s.sendall(raw)
    chunks: list[bytes] = []
    s.settimeout(4)
    while True:
        try:
            c = s.recv(65536)
        except TimeoutError:
            break
        if not c:
            break
        chunks.append(c)
    return chunks


def main() -> int:
    results: list[tuple[str, str, str]] = []  # (name, status, detail)

    def record(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, "PASS" if ok else "FAIL", detail))

    # Wait until the socket is reachable.
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=1):
                break
        except OSError:
            time.sleep(0.5)
    else:
        record("connect", False, f"socket 127.0.0.1:{PORT} never came up")
        _print_summary(results)
        return 1
    record("connect", True)

    base_headers = {"X-BlenderMCP-Token": TOKEN} if TOKEN_ENABLED else {}
    r = _send({"type": "ping_thread", "params": {}, "headers": base_headers})
    record(
        "ping_thread",
        r.get("status") == "success" and r.get("result", {}).get("status") == "pong",
        json.dumps(r)[:120],
    )

    # 2. execute_code (rounds through bpy inside Blender, exercises the
    #    transport safety wrapper without involving upstream-API bugs).
    r = _send(
        {
            "type": "execute_code",
            "params": {"code": "print('blender_smoke_ok')"},
            "headers": base_headers,
        }
    )
    inner = r.get("result", {})
    record(
        "execute_code",
        r.get("status") == "success"
        and inner.get("executed") is True
        and "blender_smoke_ok" in (inner.get("result", "") or ""),
        json.dumps(r)[:160],
    )

    # 3. Token gate: behaviour depends on whether the addon side has
    #    BLENDER_MCP_TOKEN exported. When unset, any token (or none) is
    #    accepted -- the addon does not enforce.
    wrong_r = _send(
        {
            "type": "ping_thread",
            "params": {},
            "headers": {"X-BlenderMCP-Token": "definitely-wrong"},
        }
    )
    if TOKEN_ENABLED:
        body = json.dumps(wrong_r)
        record(
            "wrong_token_rejected",
            "token_mismatch" in body,
            f"expected token_mismatch, got {body[:120]!r}",
        )
        right_r = _send(
            {
                "type": "ping_thread",
                "params": {},
                "headers": {"X-BlenderMCP-Token": TOKEN},
            }
        )
        record(
            "right_token_accepted",
            right_r.get("status") == "success",
            json.dumps(right_r)[:120],
        )
    else:
        record(
            "no_token_open_seat",
            wrong_r.get("status") == "success",
            "auth is opt-in, both keys accepted: "
            + json.dumps(wrong_r)[:80],
        )

    # 4. Payload cap: send a buffer that's guaranteed to blow past the
    #    addon's BLENDER_MCP_MAX_PAYLOAD_BYTES. We use a JSON dictionary
    #    that JSON-encodes to > 1 MiB so the timer's size check trips.
    big = {"type": "ping_thread", "params": {}, "headers": {"x": "A" * (2 * 1024 * 1024)}}
    big_payload = json.dumps(big).encode("utf-8")
    chunks = _send_buffered(big_payload)
    body = b"".join(chunks).decode("utf-8", "replace")
    rejected = "payload_too_large" in body
    record(
        "payload_cap_2mb",
        rejected,
        f"server reply {body[:200]!r}",
    )

    _print_summary(results)
    return 0 if all(r[1] == "PASS" for r in results) else 1


def _print_summary(results: list[tuple[str, str, str]]) -> None:
    print("\n=== smoke_security summary ===")
    name_w = max(len(n) for n, _, _ in results) if results else 0
    for name, status, detail in results:
        line = f"  {status}  {name:<{name_w}}"
        if detail:
            line += f"  ({detail[:120]})"
        print(line)


if __name__ == "__main__":
    sys.exit(main())
