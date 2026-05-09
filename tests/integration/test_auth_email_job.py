"""Integration tests for the send_auth_email job handler."""

import json
import uuid

import asyncpg
import pytest

from supython.jobs.context import build_job_ctx
from supython.mailer import EmailMessage
from tests.conftest import CapturingBackend


async def test_send_auth_email_handler_sends_email(pool, capturing_mailer):
    job_id = uuid.uuid4()
    async with pool.acquire() as conn:
        ctx = build_job_ctx(
            conn=conn,
            job_id=job_id,
            attempt=1,
            name="send_auth_email",
            mailer=capturing_mailer,
        )
        from supython.auth._email_job import send_auth_email

        payload = {
            "to": ["user@example.com"],
            "subject": "Reset your password",
            "text": "Use this token to reset your password: abc123",
        }
        await send_auth_email(ctx, payload)

    assert len(capturing_mailer.messages) == 1
    assert capturing_mailer.messages[0].to == ["user@example.com"]
    assert capturing_mailer.messages[0].subject == "Reset your password"


async def test_send_auth_email_handler_sends_html(pool, capturing_mailer):
    job_id = uuid.uuid4()
    async with pool.acquire() as conn:
        ctx = build_job_ctx(
            conn=conn,
            job_id=job_id,
            attempt=1,
            name="send_auth_email",
            mailer=capturing_mailer,
        )
        from supython.auth._email_job import send_auth_email

        payload = {
            "to": ["user@example.com"],
            "subject": "Test",
            "text": "plain text",
            "html": "<p>html</p>",
        }
        await send_auth_email(ctx, payload)

    assert len(capturing_mailer.messages) == 1
    assert capturing_mailer.messages[0].html == "<p>html</p>"


async def test_send_auth_email_handler_raises_on_failure(pool):
    class FailingBackend:
        async def send(self, msg):
            raise RuntimeError("SMTP down")

    job_id = uuid.uuid4()
    async with pool.acquire() as conn:
        ctx = build_job_ctx(
            conn=conn,
            job_id=job_id,
            attempt=1,
            name="send_auth_email",
            mailer=FailingBackend(),
        )
        from supython.auth._email_job import send_auth_email

        with pytest.raises(RuntimeError, match="SMTP down"):
            await send_auth_email(ctx, {"to": ["a@b.com"], "subject": "x", "text": "y"})
