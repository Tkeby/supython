"""Transport-agnostic Phoenix Channels v1 protocol helpers.

The realtime websocket endpoint speaks the Phoenix channels 5-tuple wire
format used by Supabase Realtime v2 (``vsn=1.0.0``):

    [join_ref, ref, topic, event, payload]

This module owns the framing contract (encode/decode, envelope validation),
the monotonic ref counter the server uses to tag its own pushes, and a
re-armable heartbeat timer used to detect silent client disconnects.

Everything here is pure: no Starlette, FastAPI, or ``WebSocket`` imports.
The WebSocket route in :mod:`supython.realtime.websocket` wires these
primitives to the actual transport.
"""

import asyncio
import itertools
import json
import time
from collections.abc import Callable
from typing import Any, Final

from pydantic import ValidationError

from .schemas import Frame

# ---------------------------------------------------------------------------
# Constants — Phoenix/Supabase Realtime vocabulary
# ---------------------------------------------------------------------------

# Connection-level topic used by the SDKs for heartbeats.
TOPIC_PHOENIX: Final[str] = "phoenix"

# Channel lifecycle events (topic = ``realtime:<name>``).
EVENT_PHX_JOIN: Final[str] = "phx_join"
EVENT_PHX_LEAVE: Final[str] = "phx_leave"
EVENT_PHX_REPLY: Final[str] = "phx_reply"
EVENT_PHX_CLOSE: Final[str] = "phx_close"
EVENT_PHX_ERROR: Final[str] = "phx_error"

# In-channel events.
EVENT_HEARTBEAT: Final[str] = "heartbeat"
EVENT_ACCESS_TOKEN: Final[str] = "access_token"
EVENT_BROADCAST: Final[str] = "broadcast"
EVENT_PRESENCE: Final[str] = "presence"
EVENT_PRESENCE_STATE: Final[str] = "presence_state"
EVENT_PRESENCE_DIFF: Final[str] = "presence_diff"
EVENT_POSTGRES_CHANGES: Final[str] = "postgres_changes"

# phx_reply status values.
STATUS_OK: Final[str] = "ok"
STATUS_ERROR: Final[str] = "error"


# ---------------------------------------------------------------------------
# Encode / decode
# ---------------------------------------------------------------------------


class ProtocolError(ValueError):
    """Raised for any frame that is not a well-formed Phoenix 5-tuple."""


def encode(frame: Frame) -> str:
    """Serialize a :class:`Frame` to the compact JSON string sent over the wire."""
    return json.dumps(frame.model_dump(mode="json"), separators=(",", ":"))


def decode(raw: str | bytes | bytearray) -> Frame:
    """Parse a raw text frame into a validated :class:`Frame`.

    Binary frames (``vsn=2.0.0``) are intentionally unsupported in v0.4; the
    client is expected to negotiate JSON via ``?vsn=1.0.0``.
    """
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError("Frame payload is not valid UTF-8.") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"Frame is not valid JSON: {exc.msg}") from exc

    if not isinstance(data, list):
        raise ProtocolError(
            f"Frame must be a JSON array, got {type(data).__name__}."
        )
    if len(data) != 5:
        raise ProtocolError(
            f"Frame must have exactly 5 elements [join_ref, ref, topic, event, payload], got {len(data)}."
        )

    try:
        return Frame.model_validate(data)
    except ValidationError as exc:
        raise ProtocolError(f"Frame failed validation: {exc}") from exc


# ---------------------------------------------------------------------------
# Convenience builders
# ---------------------------------------------------------------------------


def make_reply(
    *,
    join_ref: str | None,
    ref: str | None,
    topic: str,
    status: str = STATUS_OK,
    response: dict[str, Any] | None = None,
) -> Frame:
    """Build a ``phx_reply`` frame.

    ``ref`` echoes the originating request's ``ref`` so the client can
    correlate.  ``response`` defaults to ``{}`` which matches how the
    Supabase SDK parses an ack.
    """
    return Frame.build(
        join_ref=join_ref,
        ref=ref,
        topic=topic,
        event=EVENT_PHX_REPLY,
        payload={"status": status, "response": response or {}},
    )


def make_server_push(
    *,
    topic: str,
    event: str,
    payload: dict[str, Any],
) -> Frame:
    """Build a server-initiated push (``join_ref`` and ``ref`` are ``null``)."""
    return Frame.build(
        join_ref=None,
        ref=None,
        topic=topic,
        event=event,
        payload=payload,
    )


# ---------------------------------------------------------------------------
# Ref counter
# ---------------------------------------------------------------------------


class RefCounter:
    """Monotonic per-connection ref generator.

    Refs are emitted as strings because the Phoenix wire format treats them
    opaquely and the JS SDK occasionally sends non-numeric refs.  Starting
    at 1 matches the convention used by the Supabase SDK for the first
    join.
    """

    __slots__ = ("_counter",)

    def __init__(self, start: int = 1) -> None:
        self._counter: itertools.count[int] = itertools.count(start)

    def next(self) -> str:
        return str(next(self._counter))


# ---------------------------------------------------------------------------
# Heartbeat timer
# ---------------------------------------------------------------------------


Clock = Callable[[], float]


class HeartbeatTimeout:
    """Re-armable inactivity timer.

    The server does not send heartbeats; it only ensures clients send them.
    Each incoming frame calls :meth:`touch` to reset the deadline.  The
    WebSocket handler concurrently runs :meth:`wait_for_timeout` and closes
    the socket (code 1001) when it returns.

    A custom ``clock`` can be injected for deterministic unit tests.  The
    default is :func:`time.monotonic`, which is immune to wall-clock jumps.
    """

    __slots__ = ("_timeout", "_clock", "_last")

    def __init__(
        self,
        timeout_seconds: float,
        *,
        clock: Clock = time.monotonic,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        self._timeout = float(timeout_seconds)
        self._clock = clock
        self._last = clock()

    def touch(self) -> None:
        """Mark activity just observed; re-arms the timer."""
        self._last = self._clock()

    @property
    def seconds_since_last(self) -> float:
        return self._clock() - self._last

    @property
    def seconds_until_timeout(self) -> float:
        return max(0.0, self._timeout - self.seconds_since_last)

    def is_expired(self) -> bool:
        return self.seconds_since_last >= self._timeout

    async def wait_for_timeout(
        self,
        *,
        sleep: Callable[[float], Any] = asyncio.sleep,
    ) -> None:
        """Block until the timeout deadline is reached without a ``touch``.

        If :meth:`touch` is called while this coroutine is sleeping, the
        sleep naturally extends on the next iteration because the remaining
        window is recomputed from the updated ``_last``.  Returns as soon
        as the deadline has been met with no intervening touch.
        """
        while True:
            remaining = self.seconds_until_timeout
            if remaining <= 0:
                return
            await sleep(remaining)
