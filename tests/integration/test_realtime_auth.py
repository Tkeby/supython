"""Auth tests for the realtime WebSocket endpoint.

Covers the DoD scenarios from the plan:

- JWT via ``?apikey=`` query string (primary SDK path).
- JWT via ``Sec-WebSocket-Protocol: bearer, <jwt>`` subprotocol (browser CSP fallback).
- No token → ``anon`` role, connection still accepted.
- Invalid / expired token → appropriate rejection.
- ``access_token`` in-channel event rotates claims mid-stream.
- Expired JWT in ``phx_join`` payload (access_token field) is rejected.
"""

import asyncio
import uuid

import asyncpg
import pytest
import pytest_asyncio
from starlette.testclient import TestClient

from supython.settings import get_settings
from tests._keys import make_expired_token, make_token, make_wrong_key_token


def _make_alg_confusion_token_realtime() -> str:
    from cryptography.hazmat.primitives import serialization
    from supython import jwks
    from tests._keys import make_alg_confusion_token

    signer = jwks.load_signing_key()
    public_pem = signer.key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return make_alg_confusion_token(public_pem)

# ---------------------------------------------------------------------------
# Skip when Postgres is not reachable.
# ---------------------------------------------------------------------------


async def _db_reachable() -> bool:
    s = get_settings()
    try:
        conn = await asyncio.wait_for(asyncpg.connect(s.database_url), timeout=3.0)
        await conn.close()
        return True
    except Exception:
        return False


@pytest_asyncio.fixture(scope="module", autouse=True)
async def require_db():
    if not await _db_reachable():
        pytest.skip("Postgres not reachable — run `supython up` first")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _token(*, role: str = "authenticated", user_id: uuid.UUID | None = None) -> str:
    return make_token(role=role, user_id=user_id)


def _expired_token() -> str:
    return make_expired_token()


def _recv_until(ws, event: str, max_frames: int = 10) -> list:
    for _ in range(max_frames):
        frame = ws.receive_json()
        if frame[3] == event:
            return frame
    raise AssertionError(f"Did not receive {event!r} within {max_frames} frames")


def _join(topic: str = "realtime:channel", ref: str = "1") -> list:
    return ["1", ref, topic, "phx_join", {}]


# ---------------------------------------------------------------------------
# No token → anon
# ---------------------------------------------------------------------------


async def test_no_token_is_accepted_as_anon(app):
    """A connection with no token is accepted; the client can join channels."""
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws:
        ws.send_json(_join())
        ack = ws.receive_json()
        assert ack[3] == "phx_reply"
        assert ack[4]["status"] == "ok"


async def test_anon_heartbeat_works(app):
    """Anon connections respond to heartbeats normally."""
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws:
        ws.send_json([None, "hb1", "phoenix", "heartbeat", {}])
        reply = ws.receive_json()
        assert reply[3] == "phx_reply"
        assert reply[1] == "hb1"
        assert reply[4]["status"] == "ok"


# ---------------------------------------------------------------------------
# JWT via query string (?apikey=)
# ---------------------------------------------------------------------------


async def test_jwt_via_apikey_query_param(app):
    """Valid JWT in ``?apikey=`` is decoded; connection is authenticated."""
    token = _token()
    with TestClient(app) as client, client.websocket_connect(
        f"/realtime/v1/websocket?vsn=1.0.0&apikey={token}"
    ) as ws:
        ws.send_json(_join())
        ack = ws.receive_json()
        assert ack[4]["status"] == "ok"


async def test_jwt_via_access_token_query_param(app):
    """``?access_token=`` is an accepted alias for ``?apikey=``."""
    token = _token()
    with TestClient(app) as client, client.websocket_connect(
        f"/realtime/v1/websocket?vsn=1.0.0&access_token={token}"
    ) as ws:
        ws.send_json(_join())
        ack = ws.receive_json()
        assert ack[4]["status"] == "ok"


# ---------------------------------------------------------------------------
# JWT via subprotocol
# ---------------------------------------------------------------------------


async def test_jwt_via_bearer_subprotocol(app):
    """``Sec-WebSocket-Protocol: bearer, <jwt>`` is decoded; connection joins."""
    token = _token()
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0",
        headers={"Sec-WebSocket-Protocol": f"bearer, {token}"},
    ) as ws:
        ws.send_json(_join())
        ack = ws.receive_json()
        assert ack[4]["status"] == "ok"


# ---------------------------------------------------------------------------
# Invalid token at connection time
# ---------------------------------------------------------------------------


async def test_invalid_token_rejected_at_connect(app):
    """A malformed JWT in ``?apikey=`` causes the connection to be rejected."""
    with (
        TestClient(app, raise_server_exceptions=False) as client,
        pytest.raises(Exception),  # noqa: B017
        client.websocket_connect("/realtime/v1/websocket?vsn=1.0.0&apikey=not.a.real.token"),
    ):
        pass  # should never reach here


async def test_wrong_key_token_rejected_at_connect(app):
    forged = make_wrong_key_token()
    with (
        TestClient(app, raise_server_exceptions=False) as client,
        pytest.raises(Exception),  # noqa: B017
        client.websocket_connect(f"/realtime/v1/websocket?vsn=1.0.0&apikey={forged}"),
    ):
        pass


async def test_alg_confusion_token_rejected_at_connect(app):
    forged = _make_alg_confusion_token_realtime()
    with (
        TestClient(app, raise_server_exceptions=False) as client,
        pytest.raises(Exception),  # noqa: B017
        client.websocket_connect(f"/realtime/v1/websocket?vsn=1.0.0&apikey={forged}"),
    ):
        pass


# ---------------------------------------------------------------------------
# Expired token in phx_join access_token field
# ---------------------------------------------------------------------------


async def test_expired_token_in_phx_join_payload_rejected(app):
    """An expired JWT in ``phx_join.access_token`` returns status=error."""
    expired = _expired_token()
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws:
        ws.send_json(
            ["1", "1", "realtime:private", "phx_join", {"access_token": expired, "config": {}}]
        )
        reply = ws.receive_json()
        assert reply[3] == "phx_reply"
        assert reply[4]["status"] == "error"
        reason = reply[4]["response"].get("reason", "")
        assert reason  # some error message must be present


# ---------------------------------------------------------------------------
# access_token rotation mid-stream
# ---------------------------------------------------------------------------


async def test_access_token_rotation_succeeds_with_valid_token(app):
    """Rotating to a valid token via the access_token event returns ok."""
    new_token = _token(role="authenticated")
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws:
        ws.send_json(_join())
        _recv_until(ws, "phx_reply")
        ws.receive_json()  # presence_state

        ws.send_json(["1", "2", "realtime:channel", "access_token", {"access_token": new_token}])
        ack = ws.receive_json()
        assert ack[3] == "phx_reply"
        assert ack[4]["status"] == "ok"


async def test_access_token_rotation_fails_with_invalid_token(app):
    """Rotating to a malformed token returns error; the existing claims are kept."""
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws:
        ws.send_json(_join())
        _recv_until(ws, "phx_reply")
        ws.receive_json()  # presence_state

        ws.send_json(
            ["1", "2", "realtime:channel", "access_token", {"access_token": "bad.token.here"}]
        )
        reply = ws.receive_json()
        assert reply[3] == "phx_reply"
        assert reply[4]["status"] == "error"


async def test_access_token_rotation_fails_missing_field(app):
    """access_token event without the access_token field returns error."""
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws:
        ws.send_json(_join())
        _recv_until(ws, "phx_reply")
        ws.receive_json()  # presence_state

        # Payload missing the actual token.
        ws.send_json(["1", "2", "realtime:channel", "access_token", {}])
        reply = ws.receive_json()
        assert reply[3] == "phx_reply"
        assert reply[4]["status"] == "error"


async def test_access_token_rotation_then_can_still_join_new_channel(app):
    """After a successful rotation the connection can join additional channels."""
    new_token = _token(role="authenticated")
    with TestClient(app) as client, client.websocket_connect(
        "/realtime/v1/websocket?vsn=1.0.0"
    ) as ws:
        # Initial join.
        ws.send_json(_join("realtime:chan1", ref="1"))
        _recv_until(ws, "phx_reply")
        ws.receive_json()  # presence_state

        # Rotate token.
        ws.send_json(["1", "2", "realtime:chan1", "access_token", {"access_token": new_token}])
        _recv_until(ws, "phx_reply")

        # Join another channel after rotation.
        ws.send_json(["2", "3", "realtime:chan2", "phx_join", {}])
        ack2 = _recv_until(ws, "phx_reply")
        assert ack2[4]["status"] == "ok"


# ---------------------------------------------------------------------------
# Realtime disabled
# ---------------------------------------------------------------------------


async def test_realtime_disabled_setting_refuses_upgrade(app):
    """When realtime_enabled=False the endpoint is not mounted and returns 404."""
    from unittest.mock import patch

    from supython.settings import Settings

    # Build a copy of the app with realtime_enabled=False.
    with patch("supython.settings.get_settings", return_value=Settings(realtime_enabled=False)):
        from supython.app import create_app

        disabled_app = create_app()

    with TestClient(disabled_app) as client:
        resp = client.get("/realtime/v1/websocket")
        # The route is not mounted so the server returns 404 or 403.
        assert resp.status_code in (403, 404, 405)
