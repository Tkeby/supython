"""Unit tests for realtime topic validation and filter parsing.

All tests are pure Python — no database, no ASGI transport required.
"""

import pytest

from supython.realtime.schemas import JoinConfig
from supython.realtime.topics import (
    EqFilter,
    FilterError,
    InFilter,
    TopicError,
    assign_subscription_ids,
    parse_filter,
    resolved_to_subscription_schema,
    validate_topic,
)

# ---------------------------------------------------------------------------
# validate_topic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "topic,expected_name",
    [
        ("realtime:room", "room"),
        ("realtime:room-42", "room-42"),
        ("realtime:todos-for-user", "todos-for-user"),
        ("realtime:A1", "A1"),
        ("realtime:abc_def", "abc_def"),
        ("realtime:" + "a" * 64, "a" * 64),  # max-length name (64 chars)
    ],
)
def test_validate_topic_valid(topic, expected_name):
    assert validate_topic(topic) == expected_name


@pytest.mark.parametrize(
    "topic",
    [
        "phoenix",                              # reserved connection-level topic
        "realtime:",                            # empty name
        "realtime: room",                       # space in name
        "realtime:room/bad",                    # slash disallowed
        "public:todos",                         # wrong prefix
        "realtime",                             # no colon
        "",                                     # entirely empty
        "realtime:" + "a" * 65,                # name too long (65 chars)
        "realtime:-starts-with-dash",           # name must start with alnum
        "realtime:_starts-with-underscore",     # name must start with alnum
    ],
)
def test_validate_topic_invalid(topic):
    with pytest.raises(TopicError):
        validate_topic(topic)


# ---------------------------------------------------------------------------
# parse_filter — eq
# ---------------------------------------------------------------------------


def test_parse_filter_eq_string_value():
    f = parse_filter("status=eq.active")
    assert isinstance(f, EqFilter)
    assert f.column == "status"
    assert f.value == "active"
    assert f.op == "eq"


def test_parse_filter_eq_numeric_value():
    f = parse_filter("room_id=eq.42")
    assert isinstance(f, EqFilter)
    assert f.column == "room_id"
    assert f.value == "42"


def test_parse_filter_eq_uuid_value():
    uid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    f = parse_filter(f"user_id=eq.{uid}")
    assert isinstance(f, EqFilter)
    assert f.value == uid


# ---------------------------------------------------------------------------
# parse_filter — in
# ---------------------------------------------------------------------------


def test_parse_filter_in_multiple_values():
    f = parse_filter("status=in.(active,inactive,pending)")
    assert isinstance(f, InFilter)
    assert f.column == "status"
    assert f.values == ("active", "inactive", "pending")
    assert f.op == "in"


def test_parse_filter_in_single_value():
    f = parse_filter("id=in.(99)")
    assert isinstance(f, InFilter)
    assert f.values == ("99",)


def test_parse_filter_in_trims_spaces():
    f = parse_filter("id=in.(1, 2, 3)")
    assert isinstance(f, InFilter)
    assert f.values == ("1", "2", "3")


# ---------------------------------------------------------------------------
# parse_filter — invalid / unsupported
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filter_str",
    [
        "bad",                 # no operator
        "col=neq.val",         # unsupported operator
        "col=gt.5",            # unsupported operator
        "col=in.no-parens",    # 'in' without parentheses
        "col=in.()",           # empty value list
        "=eq.val",             # empty column name
        "col eq val",          # space instead of '='
    ],
)
def test_parse_filter_invalid(filter_str):
    with pytest.raises(FilterError):
        parse_filter(filter_str)


# ---------------------------------------------------------------------------
# assign_subscription_ids
# ---------------------------------------------------------------------------


def test_assign_subscription_ids_preserves_order():
    config = JoinConfig.model_validate(
        {
            "postgres_changes": [
                {"event": "INSERT", "schema": "public", "table": "messages"},
                {"event": "UPDATE", "schema": "public", "table": "messages"},
                {"event": "DELETE", "schema": "public", "table": "messages"},
            ]
        }
    )
    resolved = assign_subscription_ids(config)
    assert len(resolved) == 3
    assert resolved[0].filter_spec.event == "INSERT"
    assert resolved[1].filter_spec.event == "UPDATE"
    assert resolved[2].filter_spec.event == "DELETE"
    # IDs must be monotonically increasing.
    assert resolved[0].id < resolved[1].id < resolved[2].id


def test_assign_subscription_ids_parses_eq_filter():
    config = JoinConfig.model_validate(
        {
            "postgres_changes": [
                {
                    "event": "INSERT",
                    "schema": "public",
                    "table": "messages",
                    "filter": "room_id=eq.1",
                },
            ]
        }
    )
    resolved = assign_subscription_ids(config)
    assert len(resolved) == 1
    assert isinstance(resolved[0].parsed_filter, EqFilter)
    assert resolved[0].parsed_filter.column == "room_id"
    assert resolved[0].parsed_filter.value == "1"


def test_assign_subscription_ids_no_filter_gives_none():
    config = JoinConfig.model_validate(
        {
            "postgres_changes": [
                {"event": "*", "schema": "public", "table": "todos"},
            ]
        }
    )
    resolved = assign_subscription_ids(config)
    assert resolved[0].parsed_filter is None


def test_assign_subscription_ids_raises_on_bad_filter():
    config = JoinConfig.model_validate(
        {
            "postgres_changes": [
                {
                    "event": "INSERT",
                    "schema": "public",
                    "table": "messages",
                    "filter": "this_is_not_valid",
                },
            ]
        }
    )
    with pytest.raises(FilterError):
        assign_subscription_ids(config)


def test_assign_subscription_ids_empty_config():
    config = JoinConfig.model_validate({"postgres_changes": []})
    resolved = assign_subscription_ids(config)
    assert resolved == []


def test_assign_subscription_ids_in_filter():
    config = JoinConfig.model_validate(
        {
            "postgres_changes": [
                {
                    "event": "*",
                    "schema": "public",
                    "table": "msgs",
                    "filter": "room_id=in.(1,2,3)",
                }
            ]
        }
    )
    resolved = assign_subscription_ids(config)
    assert isinstance(resolved[0].parsed_filter, InFilter)
    assert resolved[0].parsed_filter.values == ("1", "2", "3")


# ---------------------------------------------------------------------------
# resolved_to_subscription_schema
# ---------------------------------------------------------------------------


def test_resolved_to_subscription_schema_with_filter():
    config = JoinConfig.model_validate(
        {
            "postgres_changes": [
                {
                    "event": "*",
                    "schema": "public",
                    "table": "todos",
                    "filter": "id=eq.99",
                },
            ]
        }
    )
    resolved = assign_subscription_ids(config)
    schema_obj = resolved_to_subscription_schema(resolved[0])
    assert schema_obj.id == resolved[0].id
    assert schema_obj.event == "*"
    assert schema_obj.schema_name == "public"
    assert schema_obj.table == "todos"
    assert schema_obj.filter == "id=eq.99"


def test_resolved_to_subscription_schema_no_filter():
    config = JoinConfig.model_validate(
        {
            "postgres_changes": [
                {"event": "INSERT", "schema": "auth", "table": "users"},
            ]
        }
    )
    resolved = assign_subscription_ids(config)
    schema_obj = resolved_to_subscription_schema(resolved[0])
    assert schema_obj.filter is None
    assert schema_obj.schema_name == "auth"
    assert schema_obj.table == "users"
