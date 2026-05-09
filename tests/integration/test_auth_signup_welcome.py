"""DoD demo: signup → on_signup hook fires → enqueue welcome email → worker delivers."""

import pytest
import pytest_asyncio

from supython import db
from supython.hooks import fire, on, reset
from supython.jobs.decorators import job
from supython.jobs.registry import reset_registry
from supython.jobs.service import enqueue


@pytest_asyncio.fixture
async def conn(pool):
    async with db.as_service_role() as c:
        yield c


@pytest.fixture(autouse=True)
def _fresh():
    reset()
    reset_registry()
    yield
    reset()
    reset_registry()


@pytest_asyncio.fixture(autouse=True)
async def _clean(conn):
    await conn.execute("delete from jobs.jobs")
    yield
    await conn.execute("delete from jobs.jobs")


async def test_signup_welcome_email_flow(conn, capturing_mailer):
    handled = []

    @job("send_welcome_email", version=1, accepts_payload=False, max_attempts=5)
    async def send_welcome_email(ctx):
        handled.append(ctx.name)
        await ctx.send_email(
            to="newuser@test.com",
            subject="Welcome!",
            text="Thanks for signing up.",
        )

    @on("signup")
    async def on_signup(user, ctx):
        await enqueue(
            ctx.db,
            name="send_welcome_email",
            idempotency_key=f"welcome:{user.id}",
        )

    class FakeUser:
        def __init__(self, uid):
            self.id = uid
            self.email = "newuser@test.com"

    user = FakeUser("00000000-0000-0000-0000-000000000099")

    from supython.hooks import build_hook_ctx

    hook_ctx = build_hook_ctx(conn=conn, mailer=capturing_mailer)
    await fire("signup", user, hook_ctx)

    row = await conn.fetchrow(
        "select * from jobs.jobs where name = 'send_welcome_email'"
    )
    assert row is not None

    from supython.jobs.service import claim_next, mark_succeeded

    jobs = await claim_next(conn, worker_id="test-worker")
    assert len(jobs) == 1

    from supython.jobs.context import build_job_ctx

    ctx = build_job_ctx(
        conn=conn,
        job_id=jobs[0].id,
        attempt=1,
        name="send_welcome_email",
        mailer=capturing_mailer,
    )
    await send_welcome_email(ctx)
    await mark_succeeded(conn, jobs[0].id)

    assert len(capturing_mailer.messages) == 1
    assert capturing_mailer.messages[0].subject == "Welcome!"
