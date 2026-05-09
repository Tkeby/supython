"""Unit tests for the backup job's argv composition.

Pure-Python — no DB, no subprocess.
"""

import pytest

from supython import settings as settings_module
from supython.backups._backup_job import _build_args


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    settings_module.get_settings.cache_clear()
    yield
    settings_module.get_settings.cache_clear()


def test_host_mode_uses_pg_dump_directly(monkeypatch):
    monkeypatch.setenv("BACKUP_VIA", "host")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:pw@db.example.com:6543/myapp")

    args, env, stream_stdout = _build_args(kind="full", file_path="/tmp/x.sql")

    assert args[0] == "pg_dump"
    assert "-h" in args and "db.example.com" in args
    assert "-p" in args and "6543" in args
    assert "-U" in args and "u" in args
    assert "-d" in args and "myapp" in args
    assert "-f" in args and "/tmp/x.sql" in args
    assert "--no-owner" in args and "--no-acl" in args
    assert env["PGPASSWORD"] == "pw"
    assert stream_stdout is False


def test_host_mode_appends_schema_only_flag(monkeypatch):
    monkeypatch.setenv("BACKUP_VIA", "host")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:pw@h:5432/d")

    args, _, _ = _build_args(kind="schema-only", file_path="/tmp/x.sql")

    assert "--schema-only" in args


def test_docker_mode_runs_inside_container_and_streams_stdout(monkeypatch):
    monkeypatch.setenv("BACKUP_VIA", "docker")
    monkeypatch.setenv("BACKUP_DOCKER_CONTAINER", "supython-db")
    monkeypatch.setenv("DATABASE_URL", "postgresql://supython:s3cr3t@localhost:54322/supython")

    args, env, stream_stdout = _build_args(kind="full", file_path="/host/path/x.sql")

    assert args[:3] == ["docker", "exec", "-i"]
    # PGPASSWORD must be passed to the container via -e, not the host env
    assert "-e" in args
    e_idx = args.index("-e")
    assert args[e_idx + 1] == "PGPASSWORD=s3cr3t"
    assert "supython-db" in args
    assert "pg_dump" in args
    # Critical: -f would write inside the container; the docker path must
    # stream stdout to the host file instead.
    assert "-f" not in args
    assert "-h" not in args  # connect via container's localhost
    assert stream_stdout is True
    # PGPASSWORD must NOT be in the parent env (it'd leak it to children)
    assert env.get("PGPASSWORD") != "s3cr3t" or "PGPASSWORD" not in env


def test_docker_mode_uses_configured_container_name(monkeypatch):
    monkeypatch.setenv("BACKUP_VIA", "docker")
    monkeypatch.setenv("BACKUP_DOCKER_CONTAINER", "my-prod-pg")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/d")

    args, _, _ = _build_args(kind="full", file_path="/tmp/x.sql")

    assert "my-prod-pg" in args


def test_docker_mode_without_container_raises_clear_error(monkeypatch):
    monkeypatch.setenv("BACKUP_VIA", "docker")
    monkeypatch.delenv("BACKUP_DOCKER_CONTAINER", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/d")

    with pytest.raises(RuntimeError, match="BACKUP_DOCKER_CONTAINER"):
        _build_args(kind="full", file_path="/tmp/x.sql")
