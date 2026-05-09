"""Guard against circular imports between jobs.worker and jobs.backends."""

import subprocess
import sys

IMPORT_WORKER_FIRST = (
    "from supython.jobs.worker import Worker;"
    " from supython.jobs.backends import get_backend"
)
IMPORT_BACKENDS_FIRST = (
    "from supython.jobs.backends import get_backend;"
    " from supython.jobs.worker import Worker"
)


def test_import_worker_then_backends():
    result = subprocess.run(
        [sys.executable, "-c", IMPORT_WORKER_FIRST],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"import failed: {result.stderr}"


def test_import_backends_then_worker():
    result = subprocess.run(
        [sys.executable, "-c", IMPORT_BACKENDS_FIRST],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"import failed: {result.stderr}"
