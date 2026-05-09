from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


# ---------------------------------------------------------------------------
# Wire envelope — Phoenix 5-tuple: [join_ref, ref, topic, event, payload]
# ---------------------------------------------------------------------------

_EnvelopeTuple = tuple[str | None, str | None, str, str, dict[str, Any]]


class Frame(RootModel[_EnvelopeTuple]):
    """Codec for the Phoenix channel 5-tuple wire format."""

    @property
    def join_ref(self) -> str | None:
        return self.root[0]

    @property
    def ref(self) -> str | None:
        return self.root[1]

    @property
    def topic(self) -> str:
        return self.root[2]

    @property
    def event(self) -> str:
        return self.root[3]

    @property
    def payload(self) -> dict[str, Any]:
        return self.root[4]

    @classmethod
    def build(
        cls,
        *,
        join_ref: str | None,
        ref: str | None,
        topic: str,
        event: str,
        payload: dict[str, Any],
    ) -> "Frame":
        return cls.model_validate((join_ref, ref, topic, event, payload))


# ---------------------------------------------------------------------------
# phx_join payload — config sub-models
# ---------------------------------------------------------------------------

PostgresChangesEvent = Literal["INSERT", "UPDATE", "DELETE", "*"]


class PostgresChangesFilter(BaseModel):
    """One entry in config.postgres_changes sent by the client on phx_join."""

    model_config = ConfigDict(populate_by_name=True)

    event: PostgresChangesEvent
    schema_name: str = Field(alias="schema")
    table: str
    filter: str | None = None


class BroadcastConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    self_echo: bool = Field(default=False, alias="self")
    ack: bool = False


class PresenceConfig(BaseModel):
    key: str = ""


class JoinConfig(BaseModel):
    postgres_changes: list[PostgresChangesFilter] = Field(default_factory=list)
    broadcast: BroadcastConfig = Field(default_factory=BroadcastConfig)
    presence: PresenceConfig = Field(default_factory=PresenceConfig)


class PhxJoinPayload(BaseModel):
    config: JoinConfig = Field(default_factory=JoinConfig)
    access_token: str | None = None


# ---------------------------------------------------------------------------
# phx_reply payload — join acknowledgement
# ---------------------------------------------------------------------------


class PostgresChangesSubscription(BaseModel):
    """Server-assigned subscription entry returned inside the phx_join ack."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    event: PostgresChangesEvent
    schema_name: str = Field(alias="schema")
    table: str
    filter: str | None = None


class PhxReplyPayload(BaseModel):
    status: Literal["ok", "error"]
    response: dict[str, Any] = Field(default_factory=dict)


class JoinReplyResponse(BaseModel):
    postgres_changes: list[PostgresChangesSubscription] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# postgres_changes server push
# ---------------------------------------------------------------------------


class ColumnInfo(BaseModel):
    name: str
    type: str


class PostgresChangesData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(alias="schema")
    table: str
    type: Literal["INSERT", "UPDATE", "DELETE"]
    commit_timestamp: datetime
    columns: list[ColumnInfo] = Field(default_factory=list)
    record: dict[str, Any] | None = None
    old_record: dict[str, Any] | None = None


class PostgresChangesPush(BaseModel):
    """Payload for the server-push 'postgres_changes' event."""

    ids: list[int]
    data: PostgresChangesData


# ---------------------------------------------------------------------------
# presence pushes
# ---------------------------------------------------------------------------


class PresenceState(BaseModel):
    """Full presence state pushed once on join."""

    # Maps presence key → list of metas
    presences: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class PresenceDiff(BaseModel):
    joins: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    leaves: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# REST control-plane — POST /realtime/v1/enable
# ---------------------------------------------------------------------------


class EnableTableRequest(BaseModel):
    """Body for POST /realtime/v1/enable (service-role only)."""

    # Fully qualified: "public.todos"
    table: Annotated[str, Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*$")]
    owner_column: str | None = "user_id"


class EnabledTable(BaseModel):
    """One row from realtime.enabled_tables, returned by GET /realtime/v1/info."""

    schema_name: str
    table_name: str
    pk_columns: list[str]
    owner_column: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# REST control-plane — POST /realtime/v1/broadcast/{topic}
# ---------------------------------------------------------------------------


class BroadcastRequest(BaseModel):
    """Body for POST /realtime/v1/broadcast/{topic} (service-role only).

    The REST broadcast hop lets edge functions / cron jobs push to a
    realtime channel without holding an open WebSocket.  Shape mirrors the
    ``broadcast`` event payload sent by SDK clients so subscribers receive
    an identical frame regardless of source.
    """

    event: str = Field(min_length=1, max_length=255)
    payload: dict[str, Any] = Field(default_factory=dict)


class BroadcastResponse(BaseModel):
    """Result of a REST-initiated broadcast."""

    topic: str
    delivered: int
