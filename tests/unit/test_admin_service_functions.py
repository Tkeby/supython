"""Tests for supython.admin.api.service_functions — pure Python, no DB.

Covers:
- The synthetic request scope build for invocation (body + query + headers).
- The translate / serialize_response helpers that map handler returns to the
  FunctionInvokeResponse payload.
"""

import json

import pytest
from fastapi import Response
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from supython.admin.api import service_functions
from supython.admin.errors import AdminError


class TestBuildRequest:
    async def test_body_is_delivered(self):
        body = b'{"hello": "world"}'
        req = service_functions._build_request(
            "fn", "POST", {"content-type": "application/json"}, body, None
        )
        received = await req.body()
        assert received == body
        assert (await req.json()) == {"hello": "world"}

    async def test_query_string_propagates(self):
        req = service_functions._build_request("fn", "GET", {}, b"", "x=1&y=2")
        assert req.query_params.get("x") == "1"
        assert req.query_params.get("y") == "2"

    async def test_method_uppercased(self):
        req = service_functions._build_request("fn", "POST", {}, b"", None)
        assert req.method == "POST"

    async def test_path_includes_function_name(self):
        req = service_functions._build_request("nested/inner", "GET", {}, b"", None)
        assert req.url.path == "/functions/nested/inner"

    async def test_headers_lowercased_and_content_length_added(self):
        req = service_functions._build_request("fn", "POST", {"X-Foo": "bar"}, b"abc", None)
        assert req.headers.get("x-foo") == "bar"
        assert req.headers.get("content-length") == "3"

    async def test_existing_content_length_preserved(self):
        req = service_functions._build_request(
            "fn", "POST", {"Content-Length": "5"}, b"abc", None
        )
        # The header dict carries the original value; we don't override.
        assert req.headers.get("content-length") == "5"


class TestTranslate:
    def test_response_passthrough(self):
        r = Response(content=b"hi", status_code=204)
        assert service_functions._translate(r) is r

    def test_dict_to_jsonresponse(self):
        out = service_functions._translate({"ok": True})
        assert isinstance(out, JSONResponse)
        assert json.loads(out.body) == {"ok": True}

    def test_none_to_jsonresponse(self):
        out = service_functions._translate(None)
        assert json.loads(out.body) is None

    def test_basemodel_to_jsonresponse(self):
        class M(BaseModel):
            x: int

        out = service_functions._translate(M(x=1))
        assert json.loads(out.body) == {"x": 1}

    def test_status_payload_tuple(self):
        out = service_functions._translate((201, {"ok": True}))
        assert out.status_code == 201
        assert json.loads(out.body) == {"ok": True}

    def test_bytes_to_octet_stream(self):
        out = service_functions._translate(b"\x00\x01")
        assert out.media_type == "application/octet-stream"

    def test_unsupported_raises(self):
        class NotJsonable:
            pass

        with pytest.raises(AdminError) as ei:
            service_functions._translate(NotJsonable())
        assert ei.value.code == "function_invalid_return"


class TestSerializeResponse:
    def test_json_body_decoded(self):
        r = JSONResponse({"a": 1})
        out = service_functions._serialize_response(r, 12.5)
        assert out.status == 200
        assert out.body == {"a": 1}
        assert out.body_text == '{"a":1}'
        assert out.elapsed_ms == 12.5
        assert "content-type" in {k.lower() for k in out.headers}

    def test_plaintext_body_unparsed(self):
        r = PlainTextResponse("hello world")
        out = service_functions._serialize_response(r, 0.0)
        assert out.status == 200
        assert out.body is None
        assert out.body_text == "hello world"

    def test_empty_body_safe(self):
        r = Response(status_code=204)
        out = service_functions._serialize_response(r, 0.0)
        assert out.status == 204
        assert out.body is None
        assert out.body_text == ""
