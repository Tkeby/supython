"""Tests for jobs.registry — registration, lookup, versioning."""

import pytest

from supython.jobs.decorators import cron, job
from supython.jobs.registry import JobDefinition, get_registry, reset_registry


@pytest.fixture(autouse=True)
def _fresh_registry():
    reset_registry()
    yield
    reset_registry()


def test_register_and_get():
    reg = get_registry()

    async def handler(ctx):
        pass

    reg.register_job(JobDefinition(name="email", version=1, handler=handler))
    assert reg.get("email", 1) is not None
    assert reg.get("email", 2) is None
    assert reg.get("missing", 1) is None


def test_get_latest():
    reg = get_registry()

    async def v1(ctx):
        pass

    async def v2(ctx):
        pass

    reg.register_job(JobDefinition(name="email", version=1, handler=v1))
    reg.register_job(JobDefinition(name="email", version=2, handler=v2))

    latest = reg.get_latest("email")
    assert latest is not None
    assert latest.version == 2


def test_duplicate_registration_raises():
    reg = get_registry()

    async def handler(ctx):
        pass

    reg.register_job(JobDefinition(name="email", version=1, handler=handler))
    with pytest.raises(ValueError, match="already registered"):
        reg.register_job(JobDefinition(name="email", version=1, handler=handler))


def test_job_decorator_registers():
    @job("test_job", version=1, max_attempts=5)
    async def handler(ctx, payload):
        pass

    reg = get_registry()
    defn = reg.get("test_job", 1)
    assert defn is not None
    assert defn.max_attempts == 5
    assert defn.accepts_payload is True


def test_job_decorator_no_payload():
    @job("cron_tick", version=1, accepts_payload=False)
    async def handler(ctx):
        pass

    reg = get_registry()
    defn = reg.get("cron_tick", 1)
    assert defn is not None
    assert defn.accepts_payload is False


def test_cron_decorator_registers():
    @cron("*/5 * * * *", name="cleanup", job_name="cleanup_job")
    async def handler(ctx, payload):
        pass

    reg = get_registry()
    crons = list(reg.iter_crons())
    assert len(crons) == 1
    assert crons[0].name == "cleanup"
    assert crons[0].cron_expr == "*/5 * * * *"


def test_cron_decorator_auto_registers_handler():
    """@cron must register a JobDefinition for job_name; otherwise pg_cron's
    enqueue fires a job the worker rejects with `unknown job: <job_name>`."""

    @cron("*/5 * * * *", name="cleanup", job_name="cleanup_job")
    async def handler(ctx, payload):
        pass

    reg = get_registry()
    defn = reg.get_latest("cleanup_job")
    assert defn is not None, "@cron did not auto-register a job handler"
    assert defn.handler is handler
    assert defn.version == 1


def test_cron_decorator_resolves_job_name_default():
    @cron("*/5 * * * *", name="sweep")
    async def handler(ctx, payload):
        pass

    reg = get_registry()
    crons = list(reg.iter_crons())
    assert crons[0].job_name == "sweep"
    assert reg.get_latest("sweep") is not None


def test_cron_decorator_register_handler_false():
    @cron(
        "*/5 * * * *",
        name="schedule_only",
        job_name="external",
        register_handler=False,
    )
    async def handler(ctx, payload):
        pass

    reg = get_registry()
    assert len(list(reg.iter_crons())) == 1
    assert list(reg.iter_jobs()) == []


def test_cron_decorator_forwards_job_kwargs():
    @cron(
        "*/5 * * * *",
        name="cleanup",
        job_name="cleanup_job",
        accepts_payload=False,
        max_attempts=7,
        role="authenticated",
        claims_from="actor_id",
        backoff_base_s=1.5,
        backoff_max_s=42.0,
        queue="critical",
    )
    async def handler(ctx):
        pass

    defn = get_registry().get_latest("cleanup_job")
    assert defn is not None
    assert defn.accepts_payload is False
    assert defn.max_attempts == 7
    assert defn.role == "authenticated"
    assert defn.claims_from == "actor_id"
    assert defn.backoff_base_s == 1.5
    assert defn.backoff_max_s == 42.0
    assert defn.queue == "critical"


def test_iter_jobs():
    @job("a", version=1)
    async def a(ctx, payload):
        pass

    @job("b", version=1)
    async def b(ctx, payload):
        pass

    reg = get_registry()
    names = {d.name for d in reg.iter_jobs()}
    assert names == {"a", "b"}


def test_duplicate_cron_raises():
    @cron("* * * * *", name="dup")
    async def handler(ctx):
        pass

    with pytest.raises(ValueError, match="already registered"):

        @cron("*/5 * * * *", name="dup")
        async def handler2(ctx):
            pass
