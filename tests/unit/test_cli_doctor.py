"""Filesystem tests for ``supython doctor`` JWT checks."""

import os
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from typer.testing import CliRunner

from supython import cli, jwks, settings
from supython.cli import app


@pytest.fixture(autouse=True)
def stub_database_check(monkeypatch):
    """Keep existing doctor command tests focused on JWT/PostgREST behavior."""
    monkeypatch.setattr(
        cli,
        "_check_database",
        lambda _database_url: cli._DoctorReport(
            ok=["Postgres check skipped in doctor unit test"]
        ),
    )


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("JWT_ALG", raising=False)
    monkeypatch.delenv("JWT_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("JWT_PRIVATE_KEY_PATH", raising=False)
    monkeypatch.delenv("JWT_KID", raising=False)
    monkeypatch.delenv("JWT_JWKS_PATH", raising=False)
    monkeypatch.setenv("JWT_KEYSET_MANIFEST_PATH", str(tmp_path / "keyset.json"))
    monkeypatch.setenv("JWT_KEYS_DIR", str(tmp_path / "keys"))
    settings.get_settings.cache_clear()
    jwks.clear_cache()
    yield
    settings.get_settings.cache_clear()
    jwks.clear_cache()


@pytest.fixture
def chdir(tmp_path: Path):
    prev = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(prev)


def test_doctor_flags_missing_private_key(monkeypatch):
    monkeypatch.setenv("JWT_ALG", "RS256")
    monkeypatch.setenv("JWT_PRIVATE_KEY", "")
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", "")
    settings.get_settings.cache_clear()
    jwks.clear_cache()

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 1
    output = result.output + (result.stderr or "")
    assert "set JWT_PRIVATE_KEY or JWT_PRIVATE_KEY_PATH" in output


def test_doctor_flags_alg_key_mismatch(monkeypatch, tmp_path: Path):
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    key_file = tmp_path / "jwt_private.pem"
    key_file.write_bytes(pem)
    if os.name == "posix":
        key_file.chmod(0o600)

    monkeypatch.setenv("JWT_ALG", "RS256")
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", str(key_file))
    settings.get_settings.cache_clear()
    jwks.clear_cache()

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 1
    output = result.output + (result.stderr or "")
    assert "RS256 requires an RSA private key" in output


def test_doctor_reports_postgres_unreachable(monkeypatch):
    monkeypatch.setattr(
        cli,
        "_check_database",
        lambda _database_url: cli._DoctorReport(
            failures=["Postgres unreachable at postgresql://test: connection refused"]
        ),
    )
    monkeypatch.setattr(cli, "_check_jwt", lambda _settings: cli._DoctorReport())
    monkeypatch.setattr(cli, "_check_postgrest", lambda _settings: cli._DoctorReport())

    result = CliRunner().invoke(app, ["doctor"])

    output = result.output + (result.stderr or "")
    assert result.exit_code == 1
    assert "fail: Postgres unreachable" in output
    assert "connection refused" in output


def test_doctor_reports_database_role_and_extension_failures(monkeypatch):
    monkeypatch.setattr(
        cli,
        "_check_database",
        lambda _database_url: cli._DoctorReport(
            failures=[
                "missing Postgres roles: authenticated, authenticator, service_role "
                "(run `supython up`)",
                "missing required Postgres extensions: citext",
            ],
            warnings=[
                "recommended extension missing: pg_cron "
                "(used by jobs cron + auth rate-limit prune)"
            ],
        ),
    )
    monkeypatch.setattr(cli, "_check_jwt", lambda _settings: cli._DoctorReport())
    monkeypatch.setattr(cli, "_check_postgrest", lambda _settings: cli._DoctorReport())

    result = CliRunner().invoke(app, ["doctor"])

    output = result.output + (result.stderr or "")
    assert result.exit_code == 1
    assert "missing Postgres roles" in output
    assert "authenticated" in output
    assert "authenticator" in output
    assert "service_role" in output
    assert "missing required Postgres extensions: citext" in output
    assert "warn: recommended extension missing: pg_cron" in output


def test_doctor_passes_with_generated_rs256_keypair_without_postgrest(monkeypatch, chdir: Path):
    runner = CliRunner()
    keygen = runner.invoke(app, ["keygen"])
    assert keygen.exit_code == 0, keygen.output

    monkeypatch.setenv("JWT_ALG", "RS256")
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", str(chdir / ".supython" / "jwt_private.pem"))
    monkeypatch.setenv("JWT_JWKS_PATH", str(chdir / ".supython" / "jwks.json"))
    monkeypatch.setenv("STORAGE_SIGNED_URL_SECRET", "a" * 48)
    monkeypatch.setenv("OAUTH_STATE_SECRET", "a" * 48)
    settings.get_settings.cache_clear()
    jwks.clear_cache()
    monkeypatch.setattr("supython.cli._check_postgrest_accepts_token", lambda _url: "unreachable")

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0, result.output
    assert "ok: JWT signing key loads" in result.output
    assert "warn: PostgREST not reachable" in result.output


class _FakeDoctorConn:
    def __init__(
        self,
        *,
        roles: set[str],
        extensions: set[str],
        version_num: str = "150000",
        wal_level: str = "logical",
        role_attributes: dict[str, dict[str, bool]] | None = None,
        grants_to_authenticator: set[str] | None = None,
        schema_owners: dict[str, str] | None = None,
    ) -> None:
        self.roles = roles
        self.extensions = extensions
        self.version_num = version_num
        self.wal_level = wal_level
        self._role_attributes = role_attributes or {}
        self._grants_to_authenticator = grants_to_authenticator
        self._schema_owners = schema_owners
        self.closed = False

    def _role_attr(self, role_name: str, attr: str) -> bool:
        if role_name in self._role_attributes:
            return self._role_attributes[role_name].get(attr, False)
        defaults: dict[str, dict[str, bool]] = {
            "authenticator": {"rolcanlogin": True},
            "service_role": {"rolbypassrls": True},
            "anon": {"rolcanlogin": False},
            "authenticated": {"rolcanlogin": False},
        }
        return defaults.get(role_name, {}).get(attr, False)

    async def fetchval(self, query: str, *args: object) -> str | bool | None:
        if "server_version_num" in query:
            return self.version_num
        if "wal_level" in query:
            return self.wal_level
        if "from pg_roles" in query:
            attr = query.split("select ")[1].split(" from")[0]
            role_name = args[0] if args else None
            if role_name is not None:
                return self._role_attr(str(role_name), attr)
            return False
        raise AssertionError(f"unexpected fetchval query: {query}")

    async def fetch(self, query: str, *_args: object) -> list[dict[str, str]]:
        if "from pg_roles" in query and "rolname = any" in query:
            return [{"rolname": role} for role in self.roles]
        if "from pg_extension" in query:
            return [{"extname": ext} for ext in self.extensions]
        if "pg_auth_members" in query:
            grants = self._grants_to_authenticator
            if grants is None:
                grants = {"anon", "authenticated", "service_role"} & self.roles
            return [{"roleid": child, "member": "authenticator"} for child in grants]
        if "pg_namespace" in query:
            owners = self._schema_owners
            if owners is None:
                owners = {s: "service_role" for s in ("auth", "storage", "realtime", "jobs", "supython")}
            return [{"nspname": s, "owner": o} for s, o in owners.items()]
        raise AssertionError(f"unexpected fetch query: {query}")

    async def close(self) -> None:
        self.closed = True


def test_check_database_reports_postgres_unreachable(monkeypatch):
    async def fail_connect(*_args: object, **_kwargs: object) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr(cli.asyncpg, "connect", fail_connect)

    report = cli._run_async(
        cli._check_database_async("postgresql://supython@localhost/missing")
    )

    assert report.ok == []
    assert report.warnings == []
    assert len(report.failures) == 1
    assert "Postgres unreachable" in report.failures[0]
    assert "connection refused" in report.failures[0]


def test_check_database_lists_missing_roles_and_extensions(monkeypatch):
    conn = _FakeDoctorConn(roles={"anon"}, extensions={"pgcrypto"})

    async def fake_connect(*_args: object, **_kwargs: object) -> _FakeDoctorConn:
        return conn

    monkeypatch.setattr(cli.asyncpg, "connect", fake_connect)

    report = cli._run_async(cli._check_database_async("postgresql://test"))

    failures = "\n".join(report.failures)
    warnings = "\n".join(report.warnings)
    assert "Postgres reachable (server_version_num=150000)" in report.ok
    assert "missing Postgres roles" in failures
    assert "authenticated" in failures
    assert "authenticator" in failures
    assert "service_role" in failures
    assert "missing required Postgres extensions: citext" in failures
    assert "recommended extension missing: pg_cron" in warnings
    assert conn.closed is True


def test_check_database_reports_required_roles_and_extensions(monkeypatch):
    conn = _FakeDoctorConn(
        roles={"anon", "authenticated", "service_role", "authenticator"},
        extensions={"pgcrypto", "citext", "pg_cron"},
    )

    async def fake_connect(*_args: object, **_kwargs: object) -> _FakeDoctorConn:
        return conn

    monkeypatch.setattr(cli.asyncpg, "connect", fake_connect)

    report = cli._run_async(cli._check_database_async("postgresql://test"))

    assert report.failures == []
    assert report.warnings == []
    assert "Postgres reachable (server_version_num=150000)" in report.ok
    assert "required roles present: anon, authenticated, service_role, authenticator" in report.ok
    assert "required extensions present: pgcrypto, citext" in report.ok
    assert "wal_level=logical" in report.ok
    assert "role 'anon' granted to 'authenticator'" in report.ok
    assert "role 'authenticated' granted to 'authenticator'" in report.ok
    assert "role 'service_role' granted to 'authenticator'" in report.ok
    assert conn.closed is True


def test_check_database_warns_on_non_logical_wal_level(monkeypatch):
    conn = _FakeDoctorConn(
        roles={"anon", "authenticated", "service_role", "authenticator"},
        extensions={"pgcrypto", "citext", "pg_cron"},
        wal_level="replica",
    )

    async def fake_connect(*_args: object, **_kwargs: object) -> _FakeDoctorConn:
        return conn

    monkeypatch.setattr(cli.asyncpg, "connect", fake_connect)

    report = cli._run_async(cli._check_database_async("postgresql://test"))

    assert report.failures == []
    warnings = "\n".join(report.warnings)
    assert "wal_level='replica'" in warnings
    assert "logical" in warnings
    assert conn.closed is True


def test_check_database_flags_authenticator_missing_login(monkeypatch):
    conn = _FakeDoctorConn(
        roles={"anon", "authenticated", "service_role", "authenticator"},
        extensions={"pgcrypto", "citext", "pg_cron"},
        role_attributes={"authenticator": {"rolcanlogin": False}},
    )

    async def fake_connect(*_args: object, **_kwargs: object) -> _FakeDoctorConn:
        return conn

    monkeypatch.setattr(cli.asyncpg, "connect", fake_connect)

    report = cli._run_async(cli._check_database_async("postgresql://test"))

    failures = "\n".join(report.failures)
    assert "authenticator" in failures
    assert "can login" in failures
    assert conn.closed is True


def test_check_database_flags_service_role_missing_bypassrls(monkeypatch):
    conn = _FakeDoctorConn(
        roles={"anon", "authenticated", "service_role", "authenticator"},
        extensions={"pgcrypto", "citext", "pg_cron"},
        role_attributes={"service_role": {"rolbypassrls": False}},
    )

    async def fake_connect(*_args: object, **_kwargs: object) -> _FakeDoctorConn:
        return conn

    monkeypatch.setattr(cli.asyncpg, "connect", fake_connect)

    report = cli._run_async(cli._check_database_async("postgresql://test"))

    failures = "\n".join(report.failures)
    assert "service_role" in failures
    assert "rolbypassrls" in failures
    assert conn.closed is True


def test_check_database_warns_on_anon_can_login(monkeypatch):
    conn = _FakeDoctorConn(
        roles={"anon", "authenticated", "service_role", "authenticator"},
        extensions={"pgcrypto", "citext", "pg_cron"},
        role_attributes={"anon": {"rolcanlogin": True}},
    )

    async def fake_connect(*_args: object, **_kwargs: object) -> _FakeDoctorConn:
        return conn

    monkeypatch.setattr(cli.asyncpg, "connect", fake_connect)

    report = cli._run_async(cli._check_database_async("postgresql://test"))

    assert report.failures == []
    warnings = "\n".join(report.warnings)
    assert "anon" in warnings
    assert "can login" in warnings
    assert conn.closed is True


def test_check_database_flags_missing_grants(monkeypatch):
    conn = _FakeDoctorConn(
        roles={"anon", "authenticated", "service_role", "authenticator"},
        extensions={"pgcrypto", "citext", "pg_cron"},
        grants_to_authenticator={"anon"},
    )

    async def fake_connect(*_args: object, **_kwargs: object) -> _FakeDoctorConn:
        return conn

    monkeypatch.setattr(cli.asyncpg, "connect", fake_connect)

    report = cli._run_async(cli._check_database_async("postgresql://test"))

    failures = "\n".join(report.failures)
    assert "authenticated" in failures
    assert "not granted to 'authenticator'" in failures
    assert "service_role" in failures
    assert conn.closed is True


def test_check_database_warns_on_wrong_schema_owner(monkeypatch):
    conn = _FakeDoctorConn(
        roles={"anon", "authenticated", "service_role", "authenticator"},
        extensions={"pgcrypto", "citext", "pg_cron"},
        schema_owners={
            "auth": "service_role",
            "storage": "service_role",
            "realtime": "service_role",
            "jobs": "anon",
            "supython": "service_role",
        },
    )

    async def fake_connect(*_args: object, **_kwargs: object) -> _FakeDoctorConn:
        return conn

    monkeypatch.setattr(cli.asyncpg, "connect", fake_connect)

    report = cli._run_async(cli._check_database_async("postgresql://test"))

    assert report.failures == []
    warnings = "\n".join(report.warnings)
    assert "jobs" in warnings
    assert "owned by 'anon'" in warnings
    assert conn.closed is True


class _FakeMigrationDriftConn:
    def __init__(
        self,
        *,
        has_table: bool = True,
        db_names: set[str] | None = None,
    ) -> None:
        self._has_table = has_table
        self._db_names = db_names or set()
        self.closed = False

    async def fetchval(self, query: str, *_args: object) -> bool | None:
        if "information_schema.tables" in query:
            return self._has_table
        raise AssertionError(f"unexpected fetchval: {query}")

    async def fetch(self, query: str, *_args: object) -> list[dict[str, str]]:
        if "supython.migrations" in query:
            return [{"name": n} for n in self._db_names]
        raise AssertionError(f"unexpected fetch: {query}")

    async def close(self) -> None:
        self.closed = True


def test_check_migration_drift_reports_unapplied(monkeypatch, tmp_path: Path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "0001_first.sql").write_text("-- first")
    (migrations_dir / "0002_second.sql").write_text("-- second")

    conn = _FakeMigrationDriftConn(db_names={"0001_first.sql"})

    async def fake_connect(*_args: object, **_kwargs: object):
        return conn

    monkeypatch.setattr(cli.asyncpg, "connect", fake_connect)
    monkeypatch.setattr(cli.migrate_mod, "DEFAULT_MIGRATIONS_DIR", migrations_dir)

    report = cli._run_async(cli._check_migration_drift_async("postgresql://test"))

    warnings = "\n".join(report.warnings)
    assert "1 unapplied migration(s)" in warnings
    assert "0002_second.sql" in warnings
    assert report.failures == []
    assert conn.closed is True


def test_check_migration_drift_reports_orphaned(monkeypatch, tmp_path: Path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "0001_first.sql").write_text("-- first")

    conn = _FakeMigrationDriftConn(
        db_names={"0001_first.sql", "0002_deleted.sql"}
    )

    async def fake_connect(*_args: object, **_kwargs: object):
        return conn

    monkeypatch.setattr(cli.asyncpg, "connect", fake_connect)
    monkeypatch.setattr(cli.migrate_mod, "DEFAULT_MIGRATIONS_DIR", migrations_dir)

    report = cli._run_async(cli._check_migration_drift_async("postgresql://test"))

    warnings = "\n".join(report.warnings)
    assert "1 migration(s) in DB but not on disk" in warnings
    assert "0002_deleted.sql" in warnings
    assert report.failures == []
    assert conn.closed is True


def test_check_migration_drift_clean(monkeypatch, tmp_path: Path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "0001_first.sql").write_text("-- first")

    conn = _FakeMigrationDriftConn(db_names={"0001_first.sql"})

    async def fake_connect(*_args: object, **_kwargs: object):
        return conn

    monkeypatch.setattr(cli.asyncpg, "connect", fake_connect)
    monkeypatch.setattr(cli.migrate_mod, "DEFAULT_MIGRATIONS_DIR", migrations_dir)

    report = cli._run_async(cli._check_migration_drift_async("postgresql://test"))

    assert report.warnings == []
    assert report.failures == []
    assert "all 1 migrations applied, no drift" in report.ok
    assert conn.closed is True


def test_check_migration_drift_warns_when_table_missing(monkeypatch, tmp_path: Path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "0001_first.sql").write_text("-- first")

    conn = _FakeMigrationDriftConn(has_table=False)

    async def fake_connect(*_args: object, **_kwargs: object):
        return conn

    monkeypatch.setattr(cli.asyncpg, "connect", fake_connect)
    monkeypatch.setattr(cli.migrate_mod, "DEFAULT_MIGRATIONS_DIR", migrations_dir)

    report = cli._run_async(cli._check_migration_drift_async("postgresql://test"))

    warnings = "\n".join(report.warnings)
    assert "supython.migrations table not found" in warnings
    assert conn.closed is True


def test_check_migration_drift_warns_on_unreachable_db(monkeypatch, tmp_path: Path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "0001_first.sql").write_text("-- first")

    async def fail_connect(*_args: object, **_kwargs: object):
        raise OSError("connection refused")

    monkeypatch.setattr(cli.asyncpg, "connect", fail_connect)
    monkeypatch.setattr(cli.migrate_mod, "DEFAULT_MIGRATIONS_DIR", migrations_dir)

    report = cli._run_async(cli._check_migration_drift_async("postgresql://test"))

    warnings = "\n".join(report.warnings)
    assert "cannot reach DB for migration drift check" in warnings

