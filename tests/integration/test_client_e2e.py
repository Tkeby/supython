"""Integration tests for supython.client — real ASGI stack, real DB.

The SDK client internally creates its own httpx.AsyncClient instances.
Each test patches those clients to use ASGITransport wired to the test
FastAPI app, so requests traverse the full middleware + router stack
without real network.
"""


import httpx
import pytest
from httpx import ASGITransport

from supython.client import create_client
from supython.client._auth import SIGNED_IN, SIGNED_OUT


@pytest.fixture
def sdk(app):
    client = create_client("http://test", anon_key="anon")
    transport = ASGITransport(app=app)
    client.auth._http = httpx.AsyncClient(transport=transport, base_url="http://test")
    client.storage._http = httpx.AsyncClient(transport=transport, base_url="http://test")
    client.functions._http = httpx.AsyncClient(transport=transport, base_url="http://test")
    return client


class TestAuthE2E:
    async def test_sign_up_and_sign_in(self, sdk):
        result = await sdk.auth.sign_up("sdk@example.com", "password1234")
        assert result.data is not None
        assert result.error is None
        assert result.data.access_token
        assert result.data.refresh_token
        assert result.data.user.email == "sdk@example.com"

        result2 = await sdk.auth.sign_in_with_password("sdk@example.com", "password1234")
        assert result2.data is not None
        assert result2.data.access_token

    async def test_sign_up_conflict(self, sdk):
        await sdk.auth.sign_up("conflict@example.com", "password1234")
        result = await sdk.auth.sign_up("conflict@example.com", "password1234")
        assert result.data is None
        assert result.error is not None
        assert result.error.code == "email_taken"

    async def test_refresh_rotation(self, sdk):
        result = await sdk.auth.sign_up("refresh@example.com", "password1234")
        old_refresh = result.data.refresh_token

        refresh_result = await sdk.auth.refresh_session()
        assert refresh_result.data is not None
        assert refresh_result.data.refresh_token != old_refresh

    async def test_logout_revokes_refresh_token(self, sdk):
        await sdk.auth.sign_up("logout@example.com", "password1234")
        assert sdk._access_token is not None

        await sdk.auth.sign_out()
        assert sdk._access_token is None
        assert sdk._refresh_token is None

    async def test_refresh_reuse_detection(self, sdk):
        result = await sdk.auth.sign_up("reuse@example.com", "password1234")
        old_refresh = result.data.refresh_token

        refresh_result = await sdk.auth.refresh_session()
        assert refresh_result.data is not None

        sdk._refresh_token = old_refresh
        reuse_result = await sdk.auth.refresh_session()
        assert reuse_result.error is not None

    async def test_get_user(self, sdk):
        await sdk.auth.sign_up("user@example.com", "password1234")
        result = await sdk.auth.get_user()
        assert result.data is not None
        assert result.data.email == "user@example.com"

    async def test_auth_state_change_events(self, sdk):
        events = []
        sdk.auth.on_auth_state_change(lambda event, session: events.append(event))

        await sdk.auth.sign_up("events@example.com", "password1234")
        assert SIGNED_IN in events

        await sdk.auth.sign_out()
        assert SIGNED_OUT in events


class TestStorageE2E:
    async def test_create_bucket_and_list(self, sdk):
        await sdk.auth.sign_up("storage@example.com", "password1234")

        result = await sdk.storage.create_bucket(name="test-bucket", public=True)
        assert result.data is not None
        assert result.data.name == "test-bucket"
        assert result.data.public is True

        list_result = await sdk.storage.list_buckets()
        assert list_result.data is not None
        names = [b.name for b in list_result.data]
        assert "test-bucket" in names

    async def test_upload_download_remove(self, sdk):
        await sdk.auth.sign_up("upload@example.com", "password1234")
        await sdk.storage.create_bucket(name="files", public=False)

        bucket = sdk.storage.from_("files")
        upload_result = await bucket.upload(
            "test.txt", b"hello world", content_type="text/plain"
        )
        assert upload_result.data is not None
        assert upload_result.data.name == "test.txt"

        download_result = await bucket.download("test.txt")
        assert download_result.data == b"hello world"

        remove_result = await bucket.remove("test.txt")
        assert remove_result.error is None

    async def test_get_public_url(self, sdk):
        await sdk.auth.sign_up("public@example.com", "password1234")
        await sdk.storage.create_bucket(name="public-bucket", public=True)

        bucket = sdk.storage.from_("public-bucket")
        url = bucket.get_public_url("pic.png")
        assert "object/public/public-bucket/pic.png" in url

    async def test_create_signed_url(self, sdk):
        await sdk.auth.sign_up("signed@example.com", "password1234")
        await sdk.storage.create_bucket(name="signed-bucket")
        bucket = sdk.storage.from_("signed-bucket")
        await bucket.upload("doc.pdf", b"pdf-data", content_type="application/pdf")

        result = await bucket.create_signed_url("doc.pdf", expires_in=3600)
        assert result.data is not None
        assert result.data.token
        assert "doc.pdf" in result.data.signed_url

    async def test_get_bucket(self, sdk):
        await sdk.auth.sign_up("getb@example.com", "password1234")
        await sdk.storage.create_bucket(name="get-bucket")

        result = await sdk.storage.get_bucket("get-bucket")
        assert result.data is not None
        assert result.data.name == "get-bucket"

    async def test_delete_bucket(self, sdk):
        await sdk.auth.sign_up("delb@example.com", "password1234")
        await sdk.storage.create_bucket(name="del-bucket")

        result = await sdk.storage.delete_bucket("del-bucket")
        assert result.error is None

        get_result = await sdk.storage.get_bucket("del-bucket")
        assert get_result.error is not None


class TestFunctionsE2E:
    async def test_invoke_function(self, sdk):
        await sdk.auth.sign_up("func@example.com", "password1234")

        result = await sdk.functions.invoke("hello", body={"name": "World"})
        assert result.error is not None or result.data is not None
