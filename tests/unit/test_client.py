"""Unit tests for supython.client — mock HTTP, no Docker, no Postgres."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from supython.client import (
    AuthOptions,
    ClientOptions,
    FileAuthStorage,
    MemoryAuthStorage,
    create_client,
)
from supython.client._auth import (
    SIGNED_IN,
    SIGNED_OUT,
    TOKEN_REFRESHED,
    AuthError,
    Session,
    SupythonResponse,
)
from supython.client._storage import (
    StorageBucket,
)

USER_BODY = {
    "id": "11111111-1111-1111-1111-111111111111",
    "email": "test@example.com",
    "created_at": "2025-01-01T00:00:00Z",
}

TOKEN_BODY = {
    "access_token": "at_123",
    "token_type": "bearer",
    "expires_in": 3600,
    "refresh_token": "rt_456",
    "user": USER_BODY,
}


def _json_resp(body: dict | list, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=body,
        request=MagicMock(),
    )


class TestMemoryAuthStorage:
    async def test_save_and_load_round_trip(self):
        storage = MemoryAuthStorage()
        await storage.save({"access_token": "at", "refresh_token": "rt"})
        data = await storage.load()
        assert data == {"access_token": "at", "refresh_token": "rt"}

    async def test_load_returns_none_when_empty(self):
        storage = MemoryAuthStorage()
        assert await storage.load() is None

    async def test_clear_removes_data(self):
        storage = MemoryAuthStorage()
        await storage.save({"access_token": "at", "refresh_token": "rt"})
        await storage.clear()
        assert await storage.load() is None


class TestFileAuthStorage:
    async def test_save_and_load_round_trip(self, tmp_path):
        storage = FileAuthStorage(tmp_path / "session.json")
        await storage.save({"access_token": "at", "refresh_token": "rt"})
        data = await storage.load()
        assert data == {"access_token": "at", "refresh_token": "rt"}

    async def test_load_returns_none_when_no_file(self, tmp_path):
        storage = FileAuthStorage(tmp_path / "nope.json")
        assert await storage.load() is None

    async def test_clear_empties_file(self, tmp_path):
        path = tmp_path / "session.json"
        storage = FileAuthStorage(path)
        await storage.save({"access_token": "at", "refresh_token": "rt"})
        await storage.clear()
        assert await storage.load() is None


class TestClientOptions:
    def test_defaults(self):
        opts = ClientOptions()
        assert opts.auth.auto_refresh_token is True
        assert opts.auth.persist_session is True
        assert opts.auth.storage is None


class TestCreateClient:
    def test_creates_client_with_url(self):
        client = create_client("http://localhost:8000")
        assert client.base_url == "http://localhost:8000"

    def test_strips_trailing_slash(self):
        client = create_client("http://localhost:8000/")
        assert client.base_url == "http://localhost:8000"

    def test_sets_anon_key(self):
        client = create_client("http://localhost:8000", anon_key="key123")
        assert client._anon_key == "key123"


class TestAuthClient:
    @pytest.fixture
    def client(self):
        return create_client("http://localhost:8000", anon_key="anon")

    @pytest.fixture
    def auth(self, client):
        return client.auth

    async def test_sign_up_returns_session(self, auth):
        with patch.object(auth._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(TOKEN_BODY, 201)
            result = await auth.sign_up("test@example.com", "password1234")
        assert result.data is not None
        assert result.error is None
        assert result.data.session is not None
        assert result.data.session.access_token == "at_123"
        assert result.data.session.refresh_token == "rt_456"
        assert result.data.user.email == "test@example.com"

    async def test_sign_up_pending_confirmation(self, client, auth):
        pending_body = {
            "user": TOKEN_BODY["user"],
            "confirmation_sent_at": "2026-07-21T00:00:00+00:00",
        }
        with patch.object(auth._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(pending_body, 202)
            result = await auth.sign_up("test@example.com", "password1234")
        assert result.error is None
        assert result.data is not None
        assert result.data.session is None
        assert result.data.user.email == "test@example.com"
        assert result.data.confirmation_sent_at == "2026-07-21T00:00:00+00:00"
        assert client._access_token is None

    async def test_verify_signup_sets_session(self, client, auth):
        with patch.object(auth._http, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _json_resp(TOKEN_BODY, 200)
            result = await auth.verify_signup("tok123")
        assert result.error is None
        assert result.data is not None
        assert result.data.access_token == "at_123"
        assert client._access_token == "at_123"

    async def test_resend_confirmation_is_silent(self, auth):
        with patch.object(auth._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(None, 202)
            result = await auth.resend_confirmation("test@example.com")
        assert result.error is None
        assert result.data is None

    async def test_sign_up_sets_session(self, client, auth):
        with patch.object(auth._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(TOKEN_BODY, 201)
            await auth.sign_up("test@example.com", "password1234")
        assert client._access_token == "at_123"
        assert client._refresh_token == "rt_456"

    async def test_sign_up_returns_error_on_conflict(self, auth):
        with patch.object(auth._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(
                {"detail": {"code": "email_taken", "message": "Email already registered"}},
                409,
            )
            result = await auth.sign_up("test@example.com", "password1234")
        assert result.data is None
        assert result.error is not None
        assert result.error.code == "email_taken"
        assert result.error.status == 409

    async def test_sign_in_with_password(self, auth):
        with patch.object(auth._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(TOKEN_BODY, 200)
            result = await auth.sign_in_with_password("test@example.com", "password1234")
        assert result.data is not None
        assert result.data.access_token == "at_123"

    async def test_sign_in_returns_error_on_bad_credentials(self, auth):
        with patch.object(auth._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(
                {"detail": {"code": "invalid_credentials", "message": "Invalid credentials"}},
                400,
            )
            result = await auth.sign_in_with_password("test@example.com", "wrong")
        assert result.data is None
        assert result.error is not None
        assert result.error.code == "invalid_credentials"

    async def test_sign_out_clears_session(self, client, auth):
        client.set_session("at_old", "rt_old")
        with patch.object(auth._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(None, 204)
            result = await auth.sign_out()
        assert result.error is None
        assert client._access_token is None
        assert client._refresh_token is None

    async def test_sign_out_without_session(self, client, auth):
        result = await auth.sign_out()
        assert result.data is None
        assert result.error is None

    async def test_refresh_session_updates_tokens(self, client, auth):
        client.set_session("at_old", "rt_old")
        new_body = {
            "access_token": "at_new",
            "token_type": "bearer",
            "expires_in": 3600,
            "refresh_token": "rt_new",
            "user": USER_BODY,
        }
        with patch.object(auth._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(new_body, 200)
            result = await auth.refresh_session()
        assert result.data is not None
        assert result.data.access_token == "at_new"
        assert client._access_token == "at_new"

    async def test_refresh_reuse_detection_clears_session(self, client, auth):
        client.set_session("at_old", "rt_old")
        with patch.object(auth._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(
                {"detail": {"code": "invalid_token", "message": "Token reused"}},
                401,
            )
            result = await auth.refresh_session()
        assert result.data is None
        assert result.error is not None
        assert client._access_token is None
        assert client._refresh_token is None

    async def test_get_user(self, client, auth):
        client.set_session("at_123", "rt_456")
        with patch.object(auth._http, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _json_resp(USER_BODY, 200)
            result = await auth.get_user()
        assert result.data is not None
        assert result.data.email == "test@example.com"

    async def test_get_user_without_session(self, client, auth):
        result = await auth.get_user()
        assert result.data is None
        assert result.error is not None
        assert result.error.code == "no_session"

    async def test_get_session_returns_current_state(self, client, auth):
        assert auth.get_session() is None
        client.set_session("at_123", "rt_456")
        session = auth.get_session()
        assert session is not None
        assert session.access_token == "at_123"

    async def test_on_auth_state_change(self, client, auth):
        events: list[tuple[str, Session | None]] = []
        auth.on_auth_state_change(lambda event, session: events.append((event, session)))

        with patch.object(auth._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(TOKEN_BODY, 201)
            await auth.sign_up("test@example.com", "password1234")

        assert len(events) == 1
        assert events[0][0] == SIGNED_IN
        assert events[0][1] is not None
        assert events[0][1].access_token == "at_123"

    async def test_auth_state_unsubscribe(self, client, auth):
        events: list[tuple[str, Session | None]] = []
        unsub = auth.on_auth_state_change(lambda event, session: events.append((event, session)))
        unsub()
        with patch.object(auth._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(TOKEN_BODY, 201)
            await auth.sign_up("test@example.com", "password1234")
        assert len(events) == 0

    async def test_sign_in_emits_signed_in(self, auth):
        events: list[tuple[str, Session | None]] = []
        auth.on_auth_state_change(lambda event, session: events.append((event, session)))
        with patch.object(auth._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(TOKEN_BODY, 200)
            await auth.sign_in_with_password("test@example.com", "password1234")
        assert len(events) == 1
        assert events[0][0] == SIGNED_IN

    async def test_sign_out_emits_signed_out(self, client, auth):
        client.set_session("at", "rt")
        events: list[tuple[str, Session | None]] = []
        auth.on_auth_state_change(lambda event, session: events.append((event, session)))
        with patch.object(auth._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(None, 204)
            await auth.sign_out()
        assert len(events) == 1
        assert events[0][0] == SIGNED_OUT

    async def test_refresh_emits_token_refreshed(self, client, auth):
        client.set_session("at_old", "rt_old")
        events: list[tuple[str, Session | None]] = []
        auth.on_auth_state_change(lambda event, session: events.append((event, session)))
        with patch.object(auth._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(TOKEN_BODY, 200)
            await auth.refresh_session()
        assert len(events) == 1
        assert events[0][0] == TOKEN_REFRESHED

    async def test_network_error_returns_error(self, auth):
        with patch.object(auth._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ConnectError("connection refused")
            result = await auth.sign_up("test@example.com", "password1234")
        assert result.data is None
        assert result.error is not None
        assert result.error.code == "network_error"


class TestStorageClient:
    @pytest.fixture
    def client(self):
        return create_client("http://localhost:8000", anon_key="anon")

    @pytest.fixture
    def storage(self, client):
        return client.storage

    def test_from_returns_scoped_bucket(self, storage):
        bucket = storage.from_("avatars")
        assert isinstance(bucket, StorageBucket)

    async def test_upload_sends_multipart(self, storage):
        bucket = storage.from_("test-bucket")
        obj_body = {
            "id": "22222222-2222-2222-2222-222222222222",
            "bucket_id": "33333333-3333-3333-3333-333333333333",
            "bucket": "test-bucket",
            "name": "pic.png",
            "owner": "11111111-1111-1111-1111-111111111111",
            "size": 1024,
            "mime_type": "image/png",
            "etag": "abc123",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
        with patch.object(storage._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(obj_body, 201)
            result = await bucket.upload("pic.png", b"file-data", content_type="image/png")
        assert result.data is not None
        assert result.data.name == "pic.png"
        assert result.data.size == 1024

    async def test_upload_error_returns_storage_error(self, storage):
        bucket = storage.from_("test-bucket")
        with patch.object(storage._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(
                {"detail": {"code": "object_exists", "message": "Object already exists"}}, 409
            )
            result = await bucket.upload("pic.png", b"data")
        assert result.data is None
        assert result.error is not None
        assert result.error.code == "object_exists"

    async def test_download_returns_bytes(self, storage):
        bucket = storage.from_("test-bucket")
        with patch.object(storage._http, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = httpx.Response(
                200,
                content=b"raw-bytes",
                request=MagicMock(),
            )
            result = await bucket.download("pic.png")
        assert result.data == b"raw-bytes"

    def test_get_public_url_synchronous(self, storage):
        bucket = storage.from_("avatars")
        url = bucket.get_public_url("pic.png")
        assert url == "http://localhost:8000/storage/v1/object/public/avatars/pic.png"

    async def test_create_signed_url(self, storage):
        bucket = storage.from_("test-bucket")
        signed_body = {
            "signed_url": "http://localhost:8000/storage/v1/object/signed/test-bucket/pic.png?token=tok",
            "token": "tok",
            "expires_at": "2025-01-02T00:00:00Z",
            "expires_in": 3600,
        }
        with patch.object(storage._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(signed_body, 200)
            result = await bucket.create_signed_url("pic.png", expires_in=3600)
        assert result.data is not None
        assert result.data.token == "tok"

    async def test_remove_object(self, storage):
        bucket = storage.from_("test-bucket")
        with patch.object(storage._http, "delete", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = _json_resp(None, 204)
            result = await bucket.remove("pic.png")
        assert result.data is None
        assert result.error is None

    async def test_create_bucket(self, storage):
        bucket_body = {
            "id": "33333333-3333-3333-3333-333333333333",
            "name": "test-bucket",
            "owner": "11111111-1111-1111-1111-111111111111",
            "public": False,
            "file_size_limit": None,
            "allowed_mime_types": None,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
        with patch.object(storage._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(bucket_body, 201)
            result = await storage.create_bucket(name="test-bucket")
        assert result.data is not None
        assert result.data.name == "test-bucket"

    async def test_list_buckets(self, storage):
        with patch.object(storage._http, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _json_resp([], 200)
            result = await storage.list_buckets()
        assert result.data is not None
        assert result.data == []

    async def test_get_bucket(self, storage):
        bucket_body = {
            "id": "33333333-3333-3333-3333-333333333333",
            "name": "test-bucket",
            "owner": None,
            "public": True,
            "file_size_limit": None,
            "allowed_mime_types": None,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
        with patch.object(storage._http, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _json_resp(bucket_body, 200)
            result = await storage.get_bucket("test-bucket")
        assert result.data is not None
        assert result.data.public is True

    async def test_delete_bucket(self, storage):
        with patch.object(storage._http, "delete", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = _json_resp(None, 204)
            result = await storage.delete_bucket("test-bucket")
        assert result.error is None


class TestFunctionsClient:
    @pytest.fixture
    def client(self):
        return create_client("http://localhost:8000", anon_key="anon")

    @pytest.fixture
    def functions(self, client):
        return client.functions

    async def test_invoke_sends_json_body(self, functions):
        with patch.object(functions._http, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _json_resp({"result": "hello"}, 200)
            result = await functions.invoke("hello", body={"name": "World"})
        assert result.data == {"result": "hello"}

    async def test_invoke_without_body(self, functions):
        with patch.object(functions._http, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _json_resp({"ok": True}, 200)
            result = await functions.invoke("ping")
        assert result.data == {"ok": True}

    async def test_invoke_error(self, functions):
        with patch.object(functions._http, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _json_resp(
                {"detail": {"code": "function_not_found", "message": "hello not found"}}, 404
            )
            result = await functions.invoke("hello")
        assert result.data is None
        assert result.error is not None
        assert result.error.code == "function_not_found"

    async def test_invoke_with_auth(self, client, functions):
        client.set_session("at_123", "rt_456")
        with patch.object(functions._http, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _json_resp({"ok": True}, 200)
            await functions.invoke("hello")
        call_kwargs = mock_req.call_args
        assert "Bearer at_123" in call_kwargs.kwargs.get("headers", {}).get("Authorization", "")


class TestClientComposition:
    def test_auth_headers_without_token(self):
        client = create_client("http://localhost:8000", anon_key="anon")
        headers = client._auth_headers()
        assert headers == {"apikey": "anon"}

    def test_auth_headers_with_token(self):
        client = create_client("http://localhost:8000", anon_key="anon")
        client.set_session("at_123", "rt_456")
        headers = client._auth_headers()
        assert headers == {
            "apikey": "anon",
            "Authorization": "Bearer at_123",
        }

    def test_clear_session(self):
        client = create_client("http://localhost:8000")
        client.set_session("at", "rt")
        client.clear_session()
        assert client._access_token is None
        assert client._refresh_token is None

    def test_from_raises_without_postgrest(self):
        client = create_client("http://localhost:8000")
        with pytest.raises(ImportError, match="postgrest-py"):
            client.from_("todos")

    def test_channel_raises_without_realtime(self):
        client = create_client("http://localhost:8000")
        with pytest.raises(ImportError, match="realtime"):
            client.channel("room")

    def test_rpc_raises_without_postgrest(self):
        client = create_client("http://localhost:8000")
        with pytest.raises(ImportError, match="postgrest-py"):
            client.rpc("my_func")


class TestURLBuilders:
    def test_build_rest_url(self):
        from supython.client._config import _build_rest_url
        assert _build_rest_url("http://localhost:8000") == "http://localhost:8000/rest/v1"

    def test_build_ws_url_http(self):
        from supython.client._config import _build_ws_url
        assert _build_ws_url("http://localhost:8000") == "ws://localhost:8000/realtime/v1"

    def test_build_ws_url_https(self):
        from supython.client._config import _build_ws_url
        assert _build_ws_url("https://example.com") == "wss://example.com/realtime/v1"


class TestSupythonResponse:
    def test_success(self):
        resp = SupythonResponse(data="hello", error=None)
        assert resp.data == "hello"
        assert resp.error is None

    def test_error(self):
        err = AuthError("code", "message", 400)
        resp = SupythonResponse(data=None, error=err)
        assert resp.data is None
        assert resp.error.code == "code"

    def test_defaults(self):
        resp = SupythonResponse()
        assert resp.data is None
        assert resp.error is None


class TestSessionUserCaching:
    async def test_get_session_includes_user_after_sign_in(self):
        client = create_client("http://localhost:8000", anon_key="anon")
        with patch.object(client.auth._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(TOKEN_BODY, 201)
            await client.auth.sign_up("test@example.com", "password1234")

        session = client.auth.get_session()
        assert session is not None
        assert session.user is not None
        assert session.user.email == "test@example.com"
        assert session.user.id == USER_BODY["id"]

    async def test_get_session_user_is_none_before_sign_in(self):
        client = create_client("http://localhost:8000", anon_key="anon")
        client.set_session("at", "rt")
        session = client.auth.get_session()
        assert session is not None
        assert session.user is None


class TestRestoreSession:
    def _client_with_backend(self, backend: FileAuthStorage):
        return create_client(
            "http://localhost:8000",
            anon_key="anon",
            options=ClientOptions(auth=AuthOptions(storage=backend)),
        )

    async def test_restore_session_loads_tokens_from_backend(self, tmp_path):
        backend = FileAuthStorage(tmp_path / "session.json")
        await backend.save({"access_token": "at_persisted", "refresh_token": "rt_persisted"})
        client = self._client_with_backend(backend)

        restored = await client.restore_session()
        assert restored is True
        assert client._access_token == "at_persisted"
        assert client._refresh_token == "rt_persisted"

    async def test_restore_session_returns_false_when_empty(self, tmp_path):
        backend = FileAuthStorage(tmp_path / "missing.json")
        client = self._client_with_backend(backend)
        restored = await client.restore_session()
        assert restored is False
        assert client._access_token is None

    async def test_restore_session_emits_signed_in(self, tmp_path):
        backend = FileAuthStorage(tmp_path / "session.json")
        await backend.save({"access_token": "at", "refresh_token": "rt"})
        client = self._client_with_backend(backend)

        events: list[str] = []
        client.auth.on_auth_state_change(lambda event, session: events.append(event))
        await client.restore_session()
        assert SIGNED_IN in events

    async def test_persist_session_writes_to_backend(self, tmp_path):
        backend = FileAuthStorage(tmp_path / "session.json")
        client = self._client_with_backend(backend)
        with patch.object(client.auth._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(TOKEN_BODY, 201)
            await client.auth.sign_up("test@example.com", "password1234")

        loaded = await backend.load()
        assert loaded == {"access_token": "at_123", "refresh_token": "rt_456"}

    async def test_persist_session_clears_backend_on_sign_out(self, tmp_path):
        backend = FileAuthStorage(tmp_path / "session.json")
        client = self._client_with_backend(backend)
        with patch.object(client.auth._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _json_resp(TOKEN_BODY, 201)
            await client.auth.sign_up("test@example.com", "password1234")
            mock_post.return_value = _json_resp(None, 204)
            await client.auth.sign_out()

        loaded = await backend.load()
        assert loaded is None or loaded == {}


class TestStorageBucketDynamicToken:
    """Regression: bucket headers must reflect the latest access token,
    not a snapshot taken at bucket creation time. Otherwise an auto-refresh
    leaves any pre-existing bucket reference stuck on a stale JWT."""

    async def test_bucket_picks_up_token_after_refresh(self):
        client = create_client("http://localhost:8000", anon_key="anon")
        bucket = client.storage.from_("avatars")
        client.set_session("at_old", "rt_old")

        captured: dict[str, dict[str, str]] = {}

        async def fake_post(url, **kwargs):
            captured["headers"] = dict(kwargs.get("headers") or {})
            return httpx.Response(
                201,
                json={
                    "id": "1",
                    "bucket_id": "1",
                    "bucket": "avatars",
                    "name": "p.png",
                    "owner": "u",
                    "size": 1,
                    "mime_type": None,
                    "etag": None,
                    "created_at": "x",
                    "updated_at": "x",
                },
                request=MagicMock(),
            )

        client.storage._http.post = fake_post  # type: ignore[assignment]
        await bucket.upload("p.png", b"d")
        assert captured["headers"].get("Authorization") == "Bearer at_old"

        client.set_session("at_new", "rt_new")
        await bucket.upload("p.png", b"d")
        assert captured["headers"].get("Authorization") == "Bearer at_new"


class TestFunctionsError:
    async def test_invoke_error_returns_functions_error(self):
        from supython.client import FunctionsError
        client = create_client("http://localhost:8000", anon_key="anon")
        with patch.object(client.functions._http, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _json_resp(
                {"detail": {"code": "not_found", "message": "missing"}}, 404
            )
            result = await client.functions.invoke("hello")
        assert result.error is not None
        assert isinstance(result.error, FunctionsError)
        assert result.error.code == "not_found"
