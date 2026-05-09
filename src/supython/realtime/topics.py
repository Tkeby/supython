"""Topic validation and postgres_changes filter parsing for the realtime module.

Topic grammar (A2 in the plan):
    topic := "realtime:" name
    name  := [a-zA-Z0-9][a-zA-Z0-9_-]{0,63}

The phoenix system topic ("phoenix") is also legal and is handled separately
by the WebSocket layer.  This module only deals with "realtime:*" topics.

Filter grammar (v0.4 — eq / in only):
    filter := col "=" op "." value
    op     := "eq" | "in"
    value  := any-string          (for eq)
           | "(" v1 "," v2 … ")" (for in)
"""

import itertools
import re
from dataclasses import dataclass, field
from typing import Literal

from .schemas import JoinConfig, PostgresChangesFilter, PostgresChangesSubscription

# ---------------------------------------------------------------------------
# Topic validation
# ---------------------------------------------------------------------------

_TOPIC_RE = re.compile(r"^realtime:([a-zA-Z0-9][a-zA-Z0-9_-]{0,63})$")


class TopicError(ValueError):
    """Raised when a topic string does not conform to the grammar."""


def validate_topic(topic: str) -> str:
    """Return the *name* portion of a valid ``realtime:<name>`` topic.

    Raises :class:`TopicError` for any topic that does not match the grammar.
    The reserved ``phoenix`` topic used for connection-level heartbeats is
    intentionally excluded — the WebSocket handler manages it directly.
    """
    m = _TOPIC_RE.fullmatch(topic)
    if m is None:
        raise TopicError(
            f"Invalid topic {topic!r}. "
            "Expected 'realtime:<name>' where <name> matches [a-zA-Z0-9][a-zA-Z0-9_-]{0,63}."
        )
    return m.group(1)


# ---------------------------------------------------------------------------
# postgres_changes filter parsing
# ---------------------------------------------------------------------------

_FILTER_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)=(eq|in)\.(.+)$")
_IN_BODY_RE = re.compile(r"^\((.+)\)$")


class FilterError(ValueError):
    """Raised when a filter string cannot be parsed."""


@dataclass(slots=True, frozen=True)
class EqFilter:
    column: str
    value: str
    op: Literal["eq"] = field(default="eq", init=False)


@dataclass(slots=True, frozen=True)
class InFilter:
    column: str
    values: tuple[str, ...]
    op: Literal["in"] = field(default="in", init=False)


ParsedFilter = EqFilter | InFilter


def parse_filter(filter_str: str) -> ParsedFilter:
    """Parse a PostgREST-style filter string into a typed value.

    Supported operators for v0.4:
    - ``col=eq.<value>``
    - ``col=in.(<v1>,<v2>,…)``

    Raises :class:`FilterError` for unsupported or malformed inputs.
    """
    m = _FILTER_RE.fullmatch(filter_str)
    if m is None:
        raise FilterError(
            f"Cannot parse filter {filter_str!r}. "
            "Expected 'col=eq.<val>' or 'col=in.(<v1>,<v2>,…)'."
        )
    column, op, raw_value = m.group(1), m.group(2), m.group(3)

    if op == "eq":
        return EqFilter(column=column, value=raw_value)

    # op == "in"
    body_m = _IN_BODY_RE.fullmatch(raw_value)
    if body_m is None:
        raise FilterError(
            f"'in' filter value must be wrapped in parentheses, got {raw_value!r}."
        )
    values = tuple(v.strip() for v in body_m.group(1).split(",") if v.strip())
    if not values:
        raise FilterError(f"'in' filter has an empty value list in {filter_str!r}.")
    return InFilter(column=column, values=values)


# ---------------------------------------------------------------------------
# Subscription-id assignment
# ---------------------------------------------------------------------------

# Module-level monotonic counter.  Single-process; each assigned id is unique
# for the lifetime of the server.  The broker uses these as stable handles for
# the duration of a channel join; a rejoin produces new ids.
_sub_id_counter: "itertools.count[int]" = itertools.count(1)


def _next_sub_id() -> int:
    return next(_sub_id_counter)


@dataclass(slots=True)
class ResolvedSubscription:
    """A ``postgres_changes`` filter with its server-assigned id and parsed filter."""

    id: int
    filter_spec: PostgresChangesFilter
    parsed_filter: ParsedFilter | None


def assign_subscription_ids(
    config: JoinConfig,
) -> list[ResolvedSubscription]:
    """Assign a server-local integer id to every entry in *config.postgres_changes*.

    Also eagerly parses each filter string so callers catch :class:`FilterError`
    before sending the join ack.  Entries with ``filter=None`` have
    ``parsed_filter=None``.

    Returns one :class:`ResolvedSubscription` per entry, **in the same order**
    they appear in *config.postgres_changes* (required by A3).
    """
    result: list[ResolvedSubscription] = []
    for spec in config.postgres_changes:
        parsed: ParsedFilter | None = None
        if spec.filter is not None:
            parsed = parse_filter(spec.filter)
        result.append(
            ResolvedSubscription(
                id=_next_sub_id(),
                filter_spec=spec,
                parsed_filter=parsed,
            )
        )
    return result


def resolved_to_subscription_schema(
    resolved: ResolvedSubscription,
) -> PostgresChangesSubscription:
    """Convert a :class:`ResolvedSubscription` to the Pydantic reply schema."""
    spec = resolved.filter_spec
    return PostgresChangesSubscription.model_validate(
        {
            "id": resolved.id,
            "event": spec.event,
            "schema": spec.schema_name,
            "table": spec.table,
            "filter": spec.filter,
        }
    )
