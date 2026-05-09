"""Tests for supython.admin.api.service_db — pure Python, no DB."""

from uuid import UUID, uuid4

import pytest

from supython.admin import schemas
from supython.admin.api import service_db
from supython.admin.errors import AdminError


class TestQident:
    def test_quotes_simple_identifiers(self):
        assert service_db._qident("public", "todos") == '"public"."todos"'

    def test_rejects_quote_in_schema(self):
        with pytest.raises(AdminError) as ei:
            service_db._qident('pub"lic', "todos")
        assert ei.value.code == "invalid_schema"

    def test_rejects_quote_in_table(self):
        with pytest.raises(AdminError) as ei:
            service_db._qident("public", 'to"dos')
        assert ei.value.code == "invalid_table"

    def test_rejects_semicolon(self):
        with pytest.raises(AdminError):
            service_db._qident("public; drop table x", "todos")


class TestPreviewClaims:
    def test_authenticated_requires_sub(self):
        with pytest.raises(AdminError) as ei:
            service_db.preview_claims("authenticated", None)
        assert ei.value.code == "preview_sub_required"
        assert ei.value.status == 422

    def test_authenticated_with_sub(self):
        sub = uuid4()
        claims = service_db.preview_claims("authenticated", sub)
        assert claims == {
            "role": "authenticated",
            "sub": str(sub),
            "aud": "authenticated",
        }

    def test_anon_generates_sub_when_missing(self):
        claims = service_db.preview_claims("anon", None)
        assert claims["role"] == "anon"
        assert claims["aud"] == "anon"
        # sub is a generated UUID
        UUID(claims["sub"])


class TestDdlAllowlist:
    @pytest.mark.parametrize(
        "ddl",
        [
            'create policy "p" on public.t for select using (true)',
            'CREATE POLICY p ON public.t FOR SELECT USING (true)',
            'drop policy if exists "p" on public.t',
            'alter policy "p" on public.t using (false)',
            "  create  policy p on public.t for select using (true)",
        ],
    )
    def test_allows_policy_ddl(self, ddl):
        assert service_db._DDL_ALLOWED.match(ddl) is not None

    @pytest.mark.parametrize(
        "ddl",
        [
            "drop table public.t",
            "create table x (id int)",
            "alter table public.t add column foo text",
            "select 1",
            "insert into public.t values (1)",
            "drop database supython",
        ],
    )
    def test_rejects_non_policy_ddl(self, ddl):
        assert service_db._DDL_ALLOWED.match(ddl) is None


class TestSqlExecRequest:
    def test_default_read_only_is_true(self):
        req = schemas.SqlExecRequest(statement="select 1")
        assert req.read_only is True

    def test_read_only_can_be_disabled(self):
        req = schemas.SqlExecRequest(statement="update t set x = 1", read_only=False)
        assert req.read_only is False
